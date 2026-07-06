// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {Test} from "forge-std/Test.sol";
import {IERC20Errors} from "@openzeppelin/contracts/interfaces/draft-IERC6093.sol";
import {A2ASettlement} from "../src/Settlement.sol";
import {MockTOK} from "../src/MockTOK.sol";

/// M1.3 — EIP-712 offers + atomic `fulfill` + single-use. This file is the spec for
/// invariants I2 (each offer fulfillable once) and I3 (payment and mint atomic), written
/// before the implementation (docs/04 §1: spec → tests → code).
///
/// Parity contract: the revert order and error names mirror the skeleton's
/// `FakeChain.fulfill` — expired → consumer binding → salt → funds — with signature
/// recovery slotted between salt and funds (fakes don't verify signatures, so the fake is
/// silent on where it goes; docs/04 §3). One e2e deny-path test per check already exists
/// in `e2e/tests/test_lifecycle.py`; these are their in-EVM twins.
///
/// Unlike M1.2's tests there is NO harness here: everything goes through the production
/// contract's one public door, `fulfill`. That is I1 becoming behavioral, not just
/// structural.
contract FulfillTest is Test {
    A2ASettlement internal settlement;
    MockTOK internal tok;

    // Bell must be able to SIGN in these tests, so we hold his key — anvil account #1,
    // the same identity as fixtures.BELL (asserted in setUp so drift is impossible).
    uint256 internal constant BELL_PK = 0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d;
    address internal constant BELL = 0x70997970C51812dc3A010C7d01b50e0d17dc79C8;
    address internal constant ADA = 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266;
    address internal constant CAROL = 0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC; // anvil #2

    // Canonical fixture values (a2a_interfaces.fixtures — change there or not at all).
    uint8 internal constant SERVICE_BANDWIDTH = 0;
    bytes32 internal constant RESOURCE_ID_7 = bytes32(uint256(7));
    uint64 internal constant START = 1757944800; // 14:00
    uint64 internal constant END = 1757952000; // 16:00
    uint64 internal constant VALID_UNTIL = 1757946000; // quote expiry, 14:20
    uint256 internal constant PRICE = 10e18; // 10 TOK
    bytes32 internal constant SALT = bytes32(uint256(0x5A17));
    bytes32 internal constant TERMS_HASH = 0x2222222222222222222222222222222222222222222222222222222222222222;

    function setUp() public {
        settlement = new A2ASettlement();
        tok = new MockTOK();
        // Lab money for the buyers. Deliberately NO approve() here: allowance is part of
        // each test's story (its absence IS the I3 atomicity test).
        tok.faucet(ADA, 100e18);
        tok.faucet(CAROL, 100e18);
        assertEq(vm.addr(BELL_PK), BELL); // the signing key really is Bell's identity
    }

    // --- offer construction + signing (values = fixtures.CANONICAL_OFFER) -----

    // The canonical 10-TOK open offer for ticket #7's resource (fixtures.CANONICAL_OFFER).
    function _canonicalOffer() internal view returns (A2ASettlement.Offer memory) {
        return A2ASettlement.Offer({
            provider: BELL,
            consumer: address(0), // open offer: anyone may fulfill (v0 default, docs/03 §1.4)
            serviceType: SERVICE_BANDWIDTH,
            resourceId: RESOURCE_ID_7,
            params: abi.encode(uint64(50_000_000), uint8(1)), // 50 Mbps, qos class 1
            startTime: START,
            endTime: END,
            paymentToken: address(tok),
            price: PRICE,
            validUntil: VALID_UNTIL,
            salt: SALT,
            termsHash: TERMS_HASH
        });
    }

    function _sign(A2ASettlement.Offer memory offer) internal view returns (bytes memory) {
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(BELL_PK, settlement.hashOffer(offer));
        return abi.encodePacked(r, s, v); // 65 bytes, the wire format ECDSA.recover expects
    }

    // Buyer approves the exact price and fulfills — the two-step every purchase needs.
    function _approveAndFulfill(address buyer, A2ASettlement.Offer memory offer, bytes memory sig)
        internal
        returns (uint256)
    {
        vm.prank(buyer);
        tok.approve(address(settlement), offer.price);
        vm.prank(buyer);
        return settlement.fulfill(offer, sig);
    }

    // --- the purchase: money and ticket in the same breath --------------------

    function test_fulfillPaysProviderAndMintsToBuyer() public {
        A2ASettlement.Offer memory offer = _canonicalOffer();
        uint256 id = _approveAndFulfill(ADA, offer, _sign(offer));

        assertEq(id, 1); // fresh chain: first mint is #1 ("#7" = 7th sale, see M1.2 tests)
        assertEq(settlement.ownerOf(id), ADA);
        assertEq(tok.balanceOf(ADA), 90e18); // paid 10...
        assertEq(tok.balanceOf(BELL), 10e18); // ...received by Bell, same transaction
        assertTrue(settlement.consumed(settlement.hashOffer(offer)));
    }

    function test_fulfillStoresOfferTermsVerbatim() public {
        A2ASettlement.Offer memory offer = _canonicalOffer();
        uint256 id = _approveAndFulfill(ADA, offer, _sign(offer));

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
        assertEq(issuer, BELL); // the offer's signer, not the buyer
        assertEq(serviceType, SERVICE_BANDWIDTH);
        assertEq(resourceId, RESOURCE_ID_7);
        assertEq(params, offer.params);
        assertEq(startTime, START);
        assertEq(endTime, END);
        assertEq(revoked, false);
        assertEq(termsHash, TERMS_HASH);
    }

    function test_fulfillEmitsMintedAndConsumed() public {
        A2ASettlement.Offer memory offer = _canonicalOffer();
        bytes memory sig = _sign(offer);
        bytes32 digest = settlement.hashOffer(offer);
        vm.prank(ADA);
        tok.approve(address(settlement), PRICE);

        // Order matters: fulfill emits OfferConsumed first, then EntitlementMinted.
        vm.expectEmit(address(settlement));
        emit A2ASettlement.OfferConsumed(digest);
        vm.expectEmit(address(settlement));
        emit A2ASettlement.EntitlementMinted(1, BELL, SERVICE_BANDWIDTH, ADA);

        vm.prank(ADA);
        settlement.fulfill(offer, sig);
    }

    function test_openOfferAnyoneMayFulfill() public {
        // consumer == 0x0 means "first come, first served" — Carol beats Ada to it.
        A2ASettlement.Offer memory offer = _canonicalOffer();
        uint256 id = _approveAndFulfill(CAROL, offer, _sign(offer));
        assertEq(settlement.ownerOf(id), CAROL);
    }

    // --- I2: each offer fulfillable exactly once -------------------------------

    function test_I2_replayByBuyerReverts() public {
        A2ASettlement.Offer memory offer = _canonicalOffer();
        bytes memory sig = _sign(offer);
        _approveAndFulfill(ADA, offer, sig);

        vm.prank(ADA);
        tok.approve(address(settlement), PRICE); // money and intent are there; the salt isn't
        vm.prank(ADA);
        vm.expectRevert(A2ASettlement.OfferAlreadyUsed.selector);
        settlement.fulfill(offer, sig);
    }

    function test_I2_replayByAnotherBuyerReverts() public {
        // The ledger is global, not per-buyer: Bell promised this offer once, to whoever
        // came first — Carol cannot redeem Ada's already-punched ticket stub.
        A2ASettlement.Offer memory offer = _canonicalOffer();
        bytes memory sig = _sign(offer);
        _approveAndFulfill(ADA, offer, sig);

        vm.prank(CAROL);
        tok.approve(address(settlement), PRICE);
        vm.prank(CAROL);
        vm.expectRevert(A2ASettlement.OfferAlreadyUsed.selector);
        settlement.fulfill(offer, sig);
    }

    function test_I2_freshSaltIsAFreshOffer() public {
        // Same terms, new salt = a genuinely new offer needing a new signature. This is
        // how Bell sells the same product twice without a database: the salt is the
        // ticket-stub serial number.
        A2ASettlement.Offer memory offer = _canonicalOffer();
        _approveAndFulfill(ADA, offer, _sign(offer));

        offer.salt = bytes32(uint256(0x5A18));
        uint256 id2 = _approveAndFulfill(ADA, offer, _sign(offer));
        assertEq(id2, 2);
        assertEq(settlement.ownerOf(2), ADA);
    }

    // --- I3: payment and mint are atomic — both, or neither --------------------

    function test_I3_noAllowanceRollsBackTheWholeWorld() public {
        // Ada never calls approve(), so the transferFrom inside fulfill reverts at step
        // "funds" — AFTER the salt was marked consumed. The EVM must roll back that
        // earlier write too: no ticket, no payment, salt still fresh. This is the whole
        // point of doing payment+mint in one transaction instead of two.
        A2ASettlement.Offer memory offer = _canonicalOffer();
        bytes memory sig = _sign(offer);
        bytes32 digest = settlement.hashOffer(offer);

        vm.prank(ADA);
        vm.expectRevert(
            abi.encodeWithSelector(IERC20Errors.ERC20InsufficientAllowance.selector, address(settlement), 0, PRICE)
        );
        settlement.fulfill(offer, sig);

        assertFalse(settlement.consumed(digest)); // salt unpunched...
        assertEq(tok.balanceOf(ADA), 100e18); // ...money untouched...
        vm.expectRevert(); // ...ticket never existed (ERC721NonexistentToken)
        settlement.ownerOf(1);
    }

    function test_I3_underfundedBuyerRollsBackToo() public {
        // Allowance yes, balance no — the e2e suite's "underfunded buyer" deny path.
        A2ASettlement.Offer memory offer = _canonicalOffer();
        bytes memory sig = _sign(offer);
        address mallory = makeAddr("mallory"); // has approval rights but zero TOK

        vm.prank(mallory);
        tok.approve(address(settlement), PRICE);
        vm.prank(mallory);
        vm.expectRevert(
            abi.encodeWithSelector(IERC20Errors.ERC20InsufficientBalance.selector, mallory, 0, PRICE)
        );
        settlement.fulfill(offer, sig);

        assertFalse(settlement.consumed(settlement.hashOffer(offer)));
    }

    // --- deny paths in FakeChain's revert order ---------------------------------

    function test_expiredOfferReverts() public {
        A2ASettlement.Offer memory offer = _canonicalOffer();
        bytes memory sig = _sign(offer);
        vm.warp(VALID_UNTIL + 1); // one second past the quote's shelf life

        vm.prank(ADA);
        vm.expectRevert(A2ASettlement.OfferExpired.selector);
        settlement.fulfill(offer, sig);
    }

    function test_offerStillValidAtExactValidUntil() public {
        // Boundary pinned to match FakeChain's strict `now > valid_until`: the last
        // valid second is validUntil itself.
        A2ASettlement.Offer memory offer = _canonicalOffer();
        vm.warp(VALID_UNTIL);
        uint256 id = _approveAndFulfill(ADA, offer, _sign(offer));
        assertEq(settlement.ownerOf(id), ADA);
    }

    function test_targetedOfferRejectsAnyOtherBuyer() public {
        // Bell quotes *to Ada* (consumer bound). Carol, with money and the same bytes,
        // is turned away — the offer names its buyer.
        A2ASettlement.Offer memory offer = _canonicalOffer();
        offer.consumer = ADA;
        bytes memory sig = _sign(offer);

        vm.prank(CAROL);
        tok.approve(address(settlement), PRICE);
        vm.prank(CAROL);
        vm.expectRevert(A2ASettlement.WrongConsumer.selector);
        settlement.fulfill(offer, sig);

        // ...and the named buyer sails through with the identical signature.
        uint256 id = _approveAndFulfill(ADA, offer, sig);
        assertEq(settlement.ownerOf(id), ADA);
    }

    function test_revertOrder_expiredWinsOverWrongConsumer() public {
        // Both checks would fail; the fake's order says expiry speaks first. Pinning
        // the order keeps the Foundry suite and the e2e deny-path tests one spec.
        A2ASettlement.Offer memory offer = _canonicalOffer();
        offer.consumer = ADA;
        bytes memory sig = _sign(offer);
        vm.warp(VALID_UNTIL + 1);

        vm.prank(CAROL);
        vm.expectRevert(A2ASettlement.OfferExpired.selector);
        settlement.fulfill(offer, sig);
    }

    function test_revertOrder_usedSaltWinsOverBadSignature() public {
        // A replay with a garbage signature must fail as a REPLAY (salt before
        // signature): the cheap ledger read short-circuits before ecrecover runs.
        A2ASettlement.Offer memory offer = _canonicalOffer();
        _approveAndFulfill(ADA, offer, _sign(offer));

        bytes memory garbage = abi.encodePacked(bytes32(uint256(1)), bytes32(uint256(2)), uint8(27));
        vm.prank(ADA);
        vm.expectRevert(A2ASettlement.OfferAlreadyUsed.selector);
        settlement.fulfill(offer, garbage);
    }

    function test_revertOrder_wrongConsumerWinsOverUsedSalt() public {
        // Ada redeems her bound offer; Carol then replays it. Two checks fail —
        // the fake's order says consumer binding speaks before the salt ledger.
        A2ASettlement.Offer memory offer = _canonicalOffer();
        offer.consumer = ADA;
        bytes memory sig = _sign(offer);
        _approveAndFulfill(ADA, offer, sig);

        vm.prank(CAROL);
        vm.expectRevert(A2ASettlement.WrongConsumer.selector);
        settlement.fulfill(offer, sig);
    }

    function test_revertOrder_badSignatureWinsOverNoFunds() public {
        // Broke buyer, forged offer: the forgery must be named, not the empty wallet —
        // signature verification sits before the funds pull, matching the fake's
        // checks-before-mutation shape (its funds check is the last gate too).
        A2ASettlement.Offer memory offer = _canonicalOffer();
        bytes memory sig = _sign(offer);
        offer.price = PRICE - 1;
        address pauper = makeAddr("pauper"); // no TOK, no allowance

        vm.prank(pauper);
        vm.expectRevert(A2ASettlement.BadSignature.selector);
        settlement.fulfill(offer, sig);
    }

    // --- signature integrity: any tampered field dies as BadSignature -----------

    // One helper per tamper: rebuild the canonical offer, mutate ONE field, keep Bell's
    // signature over the original — recovery then yields some other address than Bell.
    function _expectBadSignature(A2ASettlement.Offer memory tampered, bytes memory originalSig) internal {
        vm.prank(ADA);
        tok.approve(address(settlement), PRICE * 2); // generous: revert must come from the sig, not funds
        vm.prank(ADA);
        vm.expectRevert(A2ASettlement.BadSignature.selector);
        settlement.fulfill(tampered, originalSig);
    }

    function test_tamperedPriceRejected() public {
        A2ASettlement.Offer memory offer = _canonicalOffer();
        bytes memory sig = _sign(offer);
        offer.price = PRICE - 1; // a one-wei discount is still forgery
        _expectBadSignature(offer, sig);
    }

    function test_tamperedParamsRejected() public {
        // The classic self-deal: upgrade 50 Mbps to 500 Mbps after Bell signed.
        A2ASettlement.Offer memory offer = _canonicalOffer();
        bytes memory sig = _sign(offer);
        offer.params = abi.encode(uint64(500_000_000), uint8(1));
        _expectBadSignature(offer, sig);
    }

    function test_tamperedResourceIdRejected() public {
        A2ASettlement.Offer memory offer = _canonicalOffer();
        bytes memory sig = _sign(offer);
        offer.resourceId = bytes32(uint256(8)); // a different path than quoted
        _expectBadSignature(offer, sig);
    }

    function test_tamperedWindowRejected() public {
        A2ASettlement.Offer memory offer = _canonicalOffer();
        bytes memory sig = _sign(offer);
        offer.endTime = END + 2 hours; // stretch the service window
        _expectBadSignature(offer, sig);
    }

    function test_tamperedProviderRejected() public {
        // Point the payment at Carol while riding Bell's signature.
        A2ASettlement.Offer memory offer = _canonicalOffer();
        bytes memory sig = _sign(offer);
        offer.provider = CAROL;
        _expectBadSignature(offer, sig);
    }

    function test_tamperedConsumerRejected() public {
        // Unbind a targeted offer: Bell signed "for Ada only", Carol blanks the field.
        // If `consumer` ever fell out of the digest, bound offers would be open to all.
        A2ASettlement.Offer memory offer = _canonicalOffer();
        offer.consumer = ADA;
        bytes memory sig = _sign(offer);
        offer.consumer = address(0);
        vm.prank(CAROL);
        tok.approve(address(settlement), PRICE);
        vm.prank(CAROL);
        vm.expectRevert(A2ASettlement.BadSignature.selector);
        settlement.fulfill(offer, sig);
    }

    function test_tamperedServiceTypeRejected() public {
        A2ASettlement.Offer memory offer = _canonicalOffer();
        bytes memory sig = _sign(offer);
        offer.serviceType = 1; // telemetry sold as bandwidth
        _expectBadSignature(offer, sig);
    }

    function test_tamperedStartTimeRejected() public {
        A2ASettlement.Offer memory offer = _canonicalOffer();
        bytes memory sig = _sign(offer);
        offer.startTime = START - 1 hours; // open the window early
        _expectBadSignature(offer, sig);
    }

    function test_tamperedPaymentTokenRejected() public {
        // The free-mint attack: pay in a worthless token you minted yourself. If
        // `paymentToken` ever fell out of the digest, every offer would cost ~nothing.
        A2ASettlement.Offer memory offer = _canonicalOffer();
        bytes memory sig = _sign(offer);
        MockTOK worthless = new MockTOK();
        worthless.faucet(ADA, 100e18);
        offer.paymentToken = address(worthless);
        vm.prank(ADA);
        worthless.approve(address(settlement), PRICE);
        vm.prank(ADA);
        vm.expectRevert(A2ASettlement.BadSignature.selector);
        settlement.fulfill(offer, sig);
    }

    function test_tamperedValidUntilRejected() public {
        // Resurrect a stale quote by stretching its shelf life.
        A2ASettlement.Offer memory offer = _canonicalOffer();
        bytes memory sig = _sign(offer);
        offer.validUntil = VALID_UNTIL + 365 days;
        _expectBadSignature(offer, sig);
    }

    function test_tamperedSaltRejected() public {
        A2ASettlement.Offer memory offer = _canonicalOffer();
        bytes memory sig = _sign(offer);
        offer.salt = bytes32(uint256(0xDEAD)); // mint the same promise under a new serial
        _expectBadSignature(offer, sig);
    }

    function test_tamperedTermsHashRejected() public {
        A2ASettlement.Offer memory offer = _canonicalOffer();
        bytes memory sig = _sign(offer);
        offer.termsHash = bytes32(uint256(0x33)); // swap the SLA fine print
        _expectBadSignature(offer, sig);
    }

    function test_signatureByAnyoneButProviderRejected() public {
        // Right bytes, wrong pen: Carol signs Bell's offer with her own key.
        A2ASettlement.Offer memory offer = _canonicalOffer();
        uint256 carolPk = 0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a; // anvil #2
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(carolPk, settlement.hashOffer(offer));
        _expectBadSignature(offer, abi.encodePacked(r, s, v));
    }

    // --- fuzz: the properties hold for arbitrary values --------------------------

    function testFuzz_anySaltFulfillsOnceAndOnlyOnce(bytes32 salt) public {
        A2ASettlement.Offer memory offer = _canonicalOffer();
        offer.salt = salt;
        bytes memory sig = _sign(offer);

        uint256 id = _approveAndFulfill(ADA, offer, sig);
        assertEq(settlement.ownerOf(id), ADA);

        vm.prank(ADA);
        tok.approve(address(settlement), PRICE);
        vm.prank(ADA);
        vm.expectRevert(A2ASettlement.OfferAlreadyUsed.selector);
        settlement.fulfill(offer, sig);
    }

    function testFuzz_exactPriceMovesWhateverItIs(uint96 price) public {
        // uint96 keeps the faucet comfortably below uint256 overflow while spanning
        // far beyond any real balance (~7.9e28 wei).
        A2ASettlement.Offer memory offer = _canonicalOffer();
        offer.price = price;
        address buyer = makeAddr("fuzzbuyer");
        tok.faucet(buyer, price);

        // Sign BEFORE pranking: _sign calls settlement.hashOffer, an external call that
        // would silently consume the prank and leave fulfill running as the test contract.
        bytes memory sig = _sign(offer);
        vm.prank(buyer);
        tok.approve(address(settlement), price);
        vm.prank(buyer);
        settlement.fulfill(offer, sig);

        assertEq(tok.balanceOf(buyer), 0); // paid exactly price, not a wei more or less
        assertEq(tok.balanceOf(BELL), price);
    }

    function testFuzz_tamperedPriceAlwaysRejected(uint256 tamperedPrice) public {
        A2ASettlement.Offer memory offer = _canonicalOffer();
        vm.assume(tamperedPrice != offer.price);
        bytes memory sig = _sign(offer);
        offer.price = tamperedPrice;

        vm.prank(ADA);
        tok.approve(address(settlement), type(uint256).max);
        vm.prank(ADA);
        vm.expectRevert(A2ASettlement.BadSignature.selector);
        settlement.fulfill(offer, sig);
    }
}
