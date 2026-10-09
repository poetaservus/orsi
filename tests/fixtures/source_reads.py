"""Synthetic source matching the reported file's size, without private code."""


def python_source_fixture(newline="\r\n") -> bytes:
    lines = [f"# fixture {index:03d}: café π " for index in range(1, 454)]
    lines[329] = "def draw_overlay(values):"
    lines[330] = "    return sum(values) - 1"
    size = sum(len((line + newline).encode("utf-8")) for line in lines)
    padding, remainder = divmod(23_631 - size, 451)
    comment_index = 0
    for index in range(len(lines)):
        if index in (329, 330):
            continue
        lines[index] += "x" * (padding + (comment_index < remainder))
        comment_index += 1
    raw = (newline.join(lines) + newline).encode("utf-8")
    assert len(raw) == 23_631 and len(raw.splitlines()) == 453
    return raw
