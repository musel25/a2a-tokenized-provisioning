// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {ERC721} from "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {Base64} from "@openzeppelin/contracts/utils/Base64.sol";
import {Strings} from "@openzeppelin/contracts/utils/Strings.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";

/// A2ASettlement — the on-chain registry of entitlements (story ch. 2's "tickets").
///
/// Each entitlement is an ERC-721 token whose enforceable terms live in *this contract's
/// storage*, not behind a URL: the network's gatekeeper authorizes by on-chain ownership
/// alone (ch. 3), so terms that could 404 or be edited would be worthless.
///
/// M1.2 built storage + ownership; M1.3 added the one public door, `fulfill` (story
/// ch. 4's vending machine): verify the provider's EIP-712 signature, pull payment,
/// mint — all in one transaction or not at all (I3). Minting stays `internal` (`_issue`),
/// so `fulfill` remains the only mint path — invariant I1 (docs/04 §3). M1.4 completes
/// the ticket's life cycle: `revoke` (issuer-only flag, never a burn — I4/I5) and an
/// on-chain `tokenURI` rendered from storage (I7). Only the enforceable fields are
/// stored; the descriptive SLA stays off-chain behind `termsHash` (docs/03 §2.2).
contract A2ASettlement is ERC721, EIP712 {
    using SafeERC20 for IERC20;
    struct Entitlement {
        address issuer; // the provider who signed the offer (e.g. Bell)
        uint8 serviceType; // 0 = bandwidth, 1 = telemetry
        bytes32 resourceId; // opaque handle; the controller maps it to topology (ADR-005)
        bytes params; // abi-encoded per serviceType (docs/03 §4.2); opaque to this contract
        uint64 startTime;
        uint64 endTime;
        bool revoked;
        bytes32 termsHash; // keccak256 of the off-chain canonical terms_doc
    }

    /// What a provider signs and a buyer redeems — the twelve fields of docs/03 §1.4's
    /// `offer` object, in that exact order (the JSON is camelCase for the same reason:
    /// what is signed must equal what this contract verifies, byte for byte).
    struct Offer {
        address provider; // who signs, gets paid, and becomes the issuer
        address consumer; // 0x0 = open offer, anyone may fulfill; else only this buyer
        uint8 serviceType; // 0 = bandwidth, 1 = telemetry
        bytes32 resourceId;
        bytes params; // abi-encoded per serviceType; opaque here (docs/03 §4.2)
        uint64 startTime;
        uint64 endTime;
        address paymentToken;
        uint256 price;
        uint64 validUntil; // the quote's shelf life — distinct from the service window
        bytes32 salt; // the ticket-stub serial: what makes two same-terms offers distinct
        bytes32 termsHash;
    }

    // The three shared deny-path names mirror the skeleton FakeChain's exceptions
    // (docs/04 §3) so the Foundry and e2e deny tests read as one spec. The rest
    // deliberately have no twin: the funds revert is the token's own error
    // (ERC20InsufficientAllowance/Balance), BadSignature can't exist in the fake
    // (fakes don't verify signatures), and NotIssuer can't either (the fake's revoke
    // has no caller identity to check).
    error OfferExpired();
    error WrongConsumer();
    error OfferAlreadyUsed();
    error BadSignature();
    error NotIssuer();

    event EntitlementMinted(uint256 indexed id, address indexed issuer, uint8 serviceType, address indexed consumer);
    event OfferConsumed(bytes32 offerHash);
    event Revoked(uint256 indexed id);

    /// keccak256 of the EIP-712 type string. Field names and ORDER must match `Offer`
    /// above and docs/03 §1.4 exactly — one reordered word here and every signature
    /// (Foundry's and, at M1.5, Python's) recovers to a stranger.
    bytes32 public constant OFFER_TYPEHASH = keccak256(
        "Offer(address provider,address consumer,uint8 serviceType,bytes32 resourceId,bytes params,uint64 startTime,uint64 endTime,address paymentToken,uint256 price,uint64 validUntil,bytes32 salt,bytes32 termsHash)"
    );

    /// digest → already fulfilled. Keyed by the full EIP-712 digest rather than the salt
    /// alone: the digest is exactly what the signature covers, so one ledger slot per
    /// signed promise (I2). For an honest provider who randomizes salts the two readings
    /// coincide.
    mapping(bytes32 => bool) public consumed;

    /// id → terms. The auto getter returns the fields as a tuple (`bytes` included). There is
    /// no "exists" bit: an unminted id reads as an all-zero struct, so existence is judged by
    /// `ownerOf` (which reverts), never by this mapping.
    mapping(uint256 => Entitlement) public entitlements;

    /// Last issued id. Ids count from 1 (first `_issue` returns 1), matching the skeleton's
    /// FakeChain(next_id=1); "ticket #7" is therefore the 7th entitlement minted.
    uint256 private _lastId;

    /// Domain ("A2AProvisioning", "0") is pinned by docs/03 §2.1 and CLAUDE.md; the Python
    /// signer (M1.5) must reproduce it byte-for-byte or every cross-stack signature fails.
    constructor() ERC721("A2A Entitlement", "A2AENT") EIP712("A2AProvisioning", "0") {}

    /// The EIP-712 digest of `offer` under this contract's domain — the 32 bytes the
    /// provider actually signs. Public so tools (cast, the Python client) can ask the
    /// contract for ground truth instead of re-deriving it.
    function hashOffer(Offer calldata offer) public view returns (bytes32) {
        return _hashTypedDataV4(
            keccak256(
                abi.encode(
                    OFFER_TYPEHASH,
                    offer.provider,
                    offer.consumer,
                    offer.serviceType,
                    offer.resourceId,
                    // EIP-712 rule that bites everyone: dynamic types (`bytes`) enter the
                    // struct hash as their keccak256, never as raw bytes.
                    keccak256(offer.params),
                    offer.startTime,
                    offer.endTime,
                    offer.paymentToken,
                    offer.price,
                    offer.validUntil,
                    offer.salt,
                    offer.termsHash
                )
            )
        );
    }

    /// The vending machine (story ch. 4): redeem a provider-signed offer. Payment moves
    /// buyer → provider and the entitlement mints to the buyer in the same transaction;
    /// any failure anywhere reverts every effect (I3 — the EVM's rollback, free of charge).
    ///
    /// Check order is the skeleton FakeChain's — expired → consumer binding → salt →
    /// funds — with signature recovery slotted after the salt check (the fake doesn't
    /// verify signatures; after the cheap reverts is also where ecrecover costs least).
    /// Deliberately NOT checked: startTime/endTime. Buying outside the service window is
    /// legitimate (Ada buys at 13:45 for the 14:00 window); *using* the window is the
    /// controller's call at activation time, against chain time (ADR-004).
    function fulfill(Offer calldata offer, bytes calldata signature) external returns (uint256 entitlementId) {
        if (block.timestamp > offer.validUntil) revert OfferExpired();
        if (offer.consumer != address(0) && offer.consumer != msg.sender) revert WrongConsumer();
        bytes32 digest = hashOffer(offer);
        if (consumed[digest]) revert OfferAlreadyUsed();
        // Replay defense lives in the DIGEST-keyed ledger above: a mauled (high-s twin)
        // signature still signs the same digest, so it hits the same slot. OZ ECDSA
        // rejecting malleable signatures is belt on top of that, not the mechanism.
        if (ECDSA.recover(digest, signature) != offer.provider) revert BadSignature();

        // Effect before interaction: the salt is punched before the token contract (external
        // code!) runs, so a reentrant call replaying this offer dies at OfferAlreadyUsed.
        consumed[digest] = true;
        // safeTransferFrom (not transferFrom): reverts on tokens that signal failure by
        // returning false instead of reverting — otherwise a broken token could mint for free.
        IERC20(offer.paymentToken).safeTransferFrom(msg.sender, offer.provider, offer.price);
        entitlementId = _issue(
            msg.sender,
            offer.provider,
            offer.serviceType,
            offer.resourceId,
            offer.params,
            offer.startTime,
            offer.endTime,
            offer.termsHash
        );

        emit OfferConsumed(digest);
        emit EntitlementMinted(entitlementId, offer.provider, offer.serviceType, msg.sender);
    }

    /// The issuer's kill switch (story ch. 8): sets ONE bit and fires the event the
    /// controller's watcher acts on. Never a burn (I5) — the token, its owner, and its
    /// terms stay readable evidence of what was promised (I8). The owner cannot revoke:
    /// the switch belongs to the party bound by the promise, not its beneficiary.
    /// Expiry, by contrast, has no function here at all — it is *passive*; nothing
    /// happens on-chain at `endTime`, readers judge staleness against chain time
    /// (ADR-004).
    ///
    /// Re-revoking is deliberately a no-op-like success (flag re-set, event re-fired),
    /// matching FakeChain.revoke; downstream teardown is idempotent (rule 8), so a
    /// duplicate event is harmless. The issuer check doubles as the existence check:
    /// an unminted id has issuer address(0), which msg.sender can never be.
    function revoke(uint256 entitlementId) external {
        if (entitlements[entitlementId].issuer != msg.sender) revert NotIssuer();
        entitlements[entitlementId].revoked = true;
        emit Revoked(entitlementId);
    }

    /// The ticket's fine print as a self-contained `data:` URI — rendered from storage
    /// on every call, so it can never 404 and never lie (I7): revoke the ticket and the
    /// JSON flips with the flag. `params` is deliberately omitted (an ABI blob is not
    /// JSON-friendly; decoders read it from `entitlements(id)` per docs/03 §4.2);
    /// `resourceId`/`termsHash` are included so the URI alone identifies what was sold.
    function tokenURI(uint256 tokenId) public view override returns (string memory) {
        _requireOwned(tokenId); // unminted ids revert, same existence rule as ownerOf
        Entitlement storage e = entitlements[tokenId];
        string memory json = string.concat(
            '{"name":"A2A Entitlement #',
            Strings.toString(tokenId),
            '","issuer":"',
            Strings.toHexString(e.issuer),
            '","serviceType":',
            Strings.toString(e.serviceType),
            ',"resourceId":"',
            Strings.toHexString(uint256(e.resourceId), 32),
            '","startTime":',
            Strings.toString(e.startTime),
            ',"endTime":',
            Strings.toString(e.endTime),
            ',"revoked":',
            e.revoked ? "true" : "false",
            ',"termsHash":"',
            Strings.toHexString(uint256(e.termsHash), 32),
            '"}'
        );
        return string.concat("data:application/json;base64,", Base64.encode(bytes(json)));
    }

    /// Mint a fresh entitlement to `to`, freezing `issuer…termsHash` in storage forever
    /// (I6). `internal` by design (I1): the sole production caller is `fulfill`;
    /// tests reach it via SettlementHarness. `revoked` always starts false.
    function _issue(
        address to,
        address issuer,
        uint8 serviceType,
        bytes32 resourceId,
        bytes memory params,
        uint64 startTime,
        uint64 endTime,
        bytes32 termsHash
    ) internal returns (uint256 id) {
        id = ++_lastId;
        entitlements[id] = Entitlement({
            issuer: issuer,
            serviceType: serviceType,
            resourceId: resourceId,
            params: params,
            startTime: startTime,
            endTime: endTime,
            revoked: false,
            termsHash: termsHash
        });
        // _mint, not _safeMint: holders are agent EOAs, and we want no receiver callback on
        // the fulfill path (M1.3) where it would be a reentrancy surface beside transferFrom.
        _mint(to, id);
    }
}
