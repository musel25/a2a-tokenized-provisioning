// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {ERC721} from "@openzeppelin/contracts/token/ERC721/ERC721.sol";

/// A2ASettlement — the on-chain registry of entitlements (story ch. 2's "tickets").
///
/// Each entitlement is an ERC-721 token whose enforceable terms live in *this contract's
/// storage*, not behind a URL: the network's gatekeeper authorizes by on-chain ownership
/// alone (ch. 3), so terms that could 404 or be edited would be worthless.
///
/// M1.2 builds storage + ownership only. Minting is `internal` (`_issue`), so by
/// construction no public transaction can mint — invariant I1, "only `fulfill` mints"
/// (docs/04 §3). `fulfill` + payment land at M1.3; `revoke`/`tokenURI` at M1.4. Only the
/// enforceable fields are stored; the descriptive SLA stays off-chain behind `termsHash`
/// (docs/03 §2.2).
contract A2ASettlement is ERC721 {
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

    /// id → terms. The auto getter returns the fields as a tuple (`bytes` included). There is
    /// no "exists" bit: an unminted id reads as an all-zero struct, so existence is judged by
    /// `ownerOf` (which reverts), never by this mapping.
    mapping(uint256 => Entitlement) public entitlements;

    /// Last issued id. Ids count from 1 (first `_issue` returns 1), matching the skeleton's
    /// FakeChain(next_id=1); "ticket #7" is therefore the 7th entitlement minted.
    uint256 private _lastId;

    constructor() ERC721("A2A Entitlement", "A2AENT") {}

    /// Mint a fresh entitlement to `to`, freezing `issuer…termsHash` in storage forever
    /// (I6). `internal` by design (I1): the sole production caller will be `fulfill` (M1.3);
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
