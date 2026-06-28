// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

/// M1.1 toolchain hello-world. The real settlement contract arrives at M1.2;
/// this Counter exists to make transaction-vs-call and events tangible first.
contract Counter {
    uint256 public number;

    event Incremented(address indexed by, uint256 newNumber);

    function increment() external {
        number += 1;
        emit Incremented(msg.sender, number);
    }
}
