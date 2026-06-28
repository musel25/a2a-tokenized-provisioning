// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {Test} from "forge-std/Test.sol";
import {A2ASettlement} from "../src/Settlement.sol";

/// Test-only subclass that exposes the `internal` mint helper. It exists so the
/// tests can create entitlements *without* the production contract carrying a public
/// mint path — that absence is invariant I1 ("only `fulfill` mints", docs/04 §3/§5).
/// The harness lives in the test build and is never deployed; the chain only ever
/// sees A2ASettlement, which has no backdoor.
contract SettlementHarness is A2ASettlement {
    function exposed_issue(
        address to,
        address issuer,
        uint8 serviceType,
        bytes32 resourceId,
        bytes calldata params,
        uint64 startTime,
        uint64 endTime,
        bytes32 termsHash
    ) external returns (uint256) {
        return _issue(to, issuer, serviceType, resourceId, params, startTime, endTime, termsHash);
    }
}

/// M1.2 — entitlement storage + ERC-721 ownership. Proves the chapter-2 ticket is real:
/// terms frozen in contract storage, ownership tracked by ERC-721, terms bound to the
/// token and not its holder (I6). `fulfill`/payment (M1.3) and revoke/tokenURI (M1.4)
/// are out of scope here — the only way to mint is this harness.
///
/// Canonical values mirror `a2a_interfaces.fixtures` (the one source of truth, CLAUDE.md):
/// Ada buys ticket #7 from Bell — bandwidth, 50 Mbps, window 14:00–16:00.
contract SettlementTest is Test {
    SettlementHarness internal settlement;

    address internal constant BELL = 0x70997970C51812dc3A010C7d01b50e0d17dc79C8; // issuer
    address internal constant ADA = 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266; // buyer/owner

    uint8 internal constant SERVICE_BANDWIDTH = 0;
    bytes32 internal constant RESOURCE_ID_7 = bytes32(uint256(7)); // 0x…0007, ticket #7's path handle
    uint64 internal constant START = 1757944800; // 14:00, unix seconds (absolute, §1.3)
    uint64 internal constant END = 1757952000; // 16:00
    // 32 bytes of 0x22 — the placeholder termsHash from fixtures (real keccak: chainmcp, M1.5).
    bytes32 internal constant TERMS_HASH = 0x2222222222222222222222222222222222222222222222222222222222222222;

    // abi(uint64 capacityBps=50e6, uint8 qosClass=1) — two right-aligned words, == fixtures.
    bytes internal PARAMS = abi.encode(uint64(50_000_000), uint8(1));

    function setUp() public {
        settlement = new SettlementHarness();
    }

    // Issue the canonical Bell→`to` bandwidth ticket; returns its id.
    function _issueCanonical(address to) internal returns (uint256) {
        return settlement.exposed_issue(to, BELL, SERVICE_BANDWIDTH, RESOURCE_ID_7, PARAMS, START, END, TERMS_HASH);
    }

    function test_issueNumbersFromOneAndIncrements() public {
        // Ids are sequential from 1 — the same scheme the skeleton's FakeChain uses
        // (next_id=1). "Ticket #7" is therefore the 7th issue, not a chosen number.
        assertEq(_issueCanonical(ADA), 1);
        assertEq(_issueCanonical(ADA), 2);
        assertEq(_issueCanonical(ADA), 3);
    }

    function test_canonicalTicketIsTheSeventhIssue() public {
        // Bell sold six entitlements before Ada (story ch. 2); hers is #7.
        for (uint256 i = 0; i < 6; i++) {
            settlement.exposed_issue(BELL, BELL, 0, bytes32(0), hex"", 0, 0, bytes32(0));
        }
        uint256 id = _issueCanonical(ADA);
        assertEq(id, 7);
        assertEq(settlement.ownerOf(7), ADA);
    }

    function test_issueStoresAllEightFieldsVerbatim() public {
        uint256 id = _issueCanonical(ADA);
        (
            address issuer,
            uint8 serviceType,
            bytes32 resourceId,
            bytes memory params,
            uint64 startTime,
            uint64 endTime,
            bool revoked,
            bytes32 termsHash
        ) = settlement.entitlements(id);

        assertEq(issuer, BELL);
        assertEq(serviceType, SERVICE_BANDWIDTH);
        assertEq(resourceId, RESOURCE_ID_7);
        assertEq(params, PARAMS);
        assertEq(startTime, START);
        assertEq(endTime, END);
        assertEq(revoked, false); // freshly issued is never pre-revoked (I8 readability)
        assertEq(termsHash, TERMS_HASH);
    }

    function test_ownerOfReflectsMintRecipient() public {
        uint256 id = _issueCanonical(ADA);
        assertEq(settlement.ownerOf(id), ADA);
    }

    function test_I6_termsSurviveTransfer() public {
        uint256 id = _issueCanonical(ADA);

        // Ada resells the NFT to Carol. ERC-721 moves ownership; the terms must not move.
        address carol = makeAddr("carol");
        vm.prank(ADA);
        settlement.transferFrom(ADA, carol, id);

        assertEq(settlement.ownerOf(id), carol); // ownership changed…
        (
            address issuer,
            uint8 serviceType,
            bytes32 resourceId,
            bytes memory params,
            uint64 startTime,
            uint64 endTime,
            bool revoked,
            bytes32 termsHash
        ) = settlement.entitlements(id);
        // …terms did not. They are bound to the token, not to whoever holds it.
        assertEq(issuer, BELL);
        assertEq(serviceType, SERVICE_BANDWIDTH);
        assertEq(resourceId, RESOURCE_ID_7);
        assertEq(params, PARAMS);
        assertEq(startTime, START);
        assertEq(endTime, END);
        assertEq(revoked, false);
        assertEq(termsHash, TERMS_HASH);
    }

    function test_unmintedEntitlementReadsAsZeroesAndHasNoOwner() public {
        // The struct mapping has no "exists" bit: an unminted id reads as an all-zero
        // struct, NOT a revert. So existence must be judged by ownerOf (which DOES
        // revert) — a distinction the controller will rely on later (M4).
        (address issuer,, bytes32 resourceId,,,, bool revoked,) = settlement.entitlements(7);
        assertEq(issuer, address(0));
        assertEq(resourceId, bytes32(0));
        assertEq(revoked, false);

        vm.expectRevert(); // OZ ERC721: ERC721NonexistentToken(7)
        settlement.ownerOf(7);
    }
}
