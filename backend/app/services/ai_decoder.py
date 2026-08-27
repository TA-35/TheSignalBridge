"""Encapsulates calls to the AI model for message decoding.

Contract (see docs/api-contract.md): given raw message text, return the four
extracted elements (Time, Task-To-Do, Deadline, For whom) plus a category
classification bounded to the fixed enum used by the patterns table. Never
invent a value for an element the message doesn't state, return "Not
specified" instead.

Model hosting decision (hosted API vs self-hosted) is open;
"""


def decode(message: str) -> dict:
    raise NotImplementedError
