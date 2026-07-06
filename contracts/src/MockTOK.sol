// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// MockTOK — the lab's payment token (docs/03 §0: mock ERC-20 "TOK", 18 decimals).
///
/// The faucet is open on purpose: TOK is stage money for a single-operator Anvil chain,
/// and gating it behind an owner would only add key ceremony to tests and demos. Nothing
/// downstream may assume TOK is scarce — value here demonstrates *settlement mechanics*
/// (allowance, transferFrom, atomicity), not economics.
contract MockTOK is ERC20 {
    constructor() ERC20("Mock TOK", "TOK") {}

    /// Mint `amount` to `to`, no questions asked. Dev/lab only; a real deployment would
    /// use a real ERC-20 and delete this contract entirely.
    function faucet(address to, uint256 amount) external {
        _mint(to, amount);
    }
}
