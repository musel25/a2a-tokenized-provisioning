// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {Test} from "forge-std/Test.sol";
import {Base64} from "@openzeppelin/contracts/utils/Base64.sol";
import {A2ASettlement} from "../src/Settlement.sol";
import {SettlementHarness} from "./Settlement.t.sol";

/// M1.4 — the ticket ages and dies: `revoke` (I4, I5), on-chain `tokenURI` (I7), and
/// expiry-is-passive (I8). Spec written before implementation (docs/04 §1).
///
/// Story ch. 8 in two sentences: *expiry is passive* — the chain does nothing at 16:00;
/// whoever cares must read the window and act. *Revocation is active* — Bell flips a flag
/// mid-window, an event fires, and the controller that subscribed to it tears the session
/// down. Nothing is ever burned or deleted: a dead ticket stays readable evidence.
contract RevokeTest is Test {
    SettlementHarness internal settlement;

    address internal constant BELL = 0x70997970C51812dc3A010C7d01b50e0d17dc79C8; // issuer
    address internal constant ADA = 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266; // owner
    bytes32 internal constant RESOURCE_ID_7 = bytes32(uint256(7));
    uint64 internal constant START = 1757944800; // 14:00
    uint64 internal constant END = 1757952000; // 16:00
    bytes32 internal constant TERMS_HASH = 0x2222222222222222222222222222222222222222222222222222222222222222;

    uint256 internal id;

    function setUp() public {
        settlement = new SettlementHarness();
        // The harness mints here because minting mechanics are M1.3's proven ground;
        // these tests are about what happens to a ticket AFTER it exists.
        id = settlement.exposed_issue(
            ADA, BELL, 0, RESOURCE_ID_7, abi.encode(uint64(50_000_000), uint8(1)), START, END, TERMS_HASH
        );
    }

    // --- I4: only the issuer may revoke -----------------------------------

    function test_I4_issuerRevokeSetsFlagAndEmits() public {
        vm.expectEmit(address(settlement));
        emit A2ASettlement.Revoked(id);
        vm.prank(BELL);
        settlement.revoke(id);

        (,,,,,, bool revoked,) = settlement.entitlements(id);
        assertTrue(revoked);
    }

    function test_I4_ownerCannotRevoke() public {
        // Ada OWNS the ticket but did not issue it — the kill switch belongs to the
        // party who signed the promise, not the one holding the benefit.
        vm.prank(ADA);
        vm.expectRevert(A2ASettlement.NotIssuer.selector);
        settlement.revoke(id);
    }

    function test_I4_strangerCannotRevoke() public {
        vm.prank(makeAddr("mallory"));
        vm.expectRevert(A2ASettlement.NotIssuer.selector);
        settlement.revoke(id);
    }

    function test_revokeUnmintedIdReverts() public {
        // entitlements[99].issuer is address(0) — nobody is that issuer, so the same
        // NotIssuer gate also rejects ids that never existed.
        vm.prank(BELL);
        vm.expectRevert(A2ASettlement.NotIssuer.selector);
        settlement.revoke(99);
    }

    function test_revokeTwiceIsIdempotent() public {
        // Parity with FakeChain.revoke (no already-revoked guard) and with rule 8's
        // spirit: the second revoke re-asserts a truth, it doesn't error. Downstream
        // teardown is idempotent too, so a double event is harmless.
        vm.startPrank(BELL);
        settlement.revoke(id);
        settlement.revoke(id);
        vm.stopPrank();
        (,,,,,, bool revoked,) = settlement.entitlements(id);
        assertTrue(revoked);
    }

    // --- I5 + I8: revoke is a flag; the dead stay readable ------------------

    function test_I5_revokeDoesNotBurnOrRewriteTerms() public {
        vm.prank(BELL);
        settlement.revoke(id);

        assertEq(settlement.ownerOf(id), ADA); // still Ada's token — no burn
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
        assertEq(issuer, BELL); // every term still in place, readable evidence (I8)
        assertEq(serviceType, 0);
        assertEq(resourceId, RESOURCE_ID_7);
        assertEq(params, abi.encode(uint64(50_000_000), uint8(1)));
        assertEq(startTime, START);
        assertEq(endTime, END);
        assertTrue(revoked); // exactly ONE bit changed
        assertEq(termsHash, TERMS_HASH);
    }

    function test_I8_expiryIsPassive_chainDoesNothingAt1600() public {
        // Time-travel far past endTime. No function is called, and none needs to be:
        // the record is byte-for-byte what it was. "Expired" is a judgment readers
        // make against chain time (the controller's job, M4) — not a state transition.
        string memory uriBefore = settlement.tokenURI(id);
        vm.warp(END + 30 days);

        assertEq(settlement.ownerOf(id), ADA);
        string memory uriAfter = settlement.tokenURI(id);
        assertEq(uriAfter, uriBefore); // nothing on the chain moved at 16:00
        (,,,,, uint64 endTime, bool revoked,) = settlement.entitlements(id);
        assertTrue(block.timestamp > endTime); // any reader can now judge it expired
        assertFalse(revoked); // expired ≠ revoked — independent facts
    }

    // --- I7: tokenURI is the storage, restated ------------------------------

    function test_I7_tokenURIDerivesPurelyFromStorage() public view {
        // Rebuild the expected JSON from the same storage the contract reads. If the
        // two ever diverge, tokenURI invented or dropped a fact — that's the invariant.
        string memory expectedJson = string.concat(
            '{"name":"A2A Entitlement #1",',
            '"issuer":"0x70997970c51812dc3a010c7d01b50e0d17dc79c8",',
            '"serviceType":0,',
            '"resourceId":"0x0000000000000000000000000000000000000000000000000000000000000007",',
            '"startTime":1757944800,"endTime":1757952000,',
            '"revoked":false,',
            '"termsHash":"0x2222222222222222222222222222222222222222222222222222222222222222"}'
        );
        assertEq(
            settlement.tokenURI(id),
            string.concat("data:application/json;base64,", Base64.encode(bytes(expectedJson)))
        );
    }

    function test_I7_tokenURIReflectsRevocation() public {
        // The fine print is live storage, not a snapshot: revoke, and the rendered
        // JSON flips with it. (This is what "no web server to 404" buys — ch. 8.)
        vm.prank(BELL);
        settlement.revoke(id);
        // spot-check the decoded payload rather than re-deriving the whole string
        string memory uri = settlement.tokenURI(id);
        string memory json = string(Base64.decode(_stripDataPrefix(uri)));
        assertTrue(vm.keyExistsJson(json, ".revoked"));
        assertTrue(vm.parseJsonBool(json, ".revoked"));
        assertEq(vm.parseJsonUint(json, ".endTime"), END);
    }

    function test_tokenURIUnmintedIdReverts() public {
        // Same existence rule the controller learned in M1.2: unminted ids revert via
        // ownerOf semantics, they don't render an all-zero ticket.
        vm.expectRevert();
        settlement.tokenURI(42);
    }

    function _stripDataPrefix(string memory uri) internal pure returns (string memory) {
        bytes memory b = bytes(uri);
        bytes memory prefix = bytes("data:application/json;base64,");
        bytes memory out = new bytes(b.length - prefix.length);
        for (uint256 i = 0; i < out.length; i++) {
            out[i] = b[i + prefix.length];
        }
        return string(out);
    }
}
