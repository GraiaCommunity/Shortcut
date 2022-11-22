from __future__ import annotations

import re

from graia.amnesia.message import Element, MessageChain, Text


def chain(elements: list[Element]) -> MessageChain:
    from graia.amnesia import message

    return message.__message_chain_class__(elements)


def text(string: str) -> Text:
    from graia.amnesia import message

    return message.__text_element_class__(string)


def map_chain(chain: MessageChain) -> tuple[str, dict[str, Element]]:
    elem_mapping: dict[str, Element] = {}
    elem_str_list: list[str] = []
    for i, elem in enumerate(chain.content):
        if not isinstance(elem, Text):
            elem_mapping[str(i)] = elem
            elem_str_list.append(f"\x02{i}_{elem.__class__.__name__}\x03")
        else:
            elem_str_list.append(elem.text)
    return "".join(elem_str_list), elem_mapping


__element_pattern = re.compile("(\x02\\w+\x03)")


def unmap_chain(string: str, mapping: dict[str, Element]) -> MessageChain:
    elements: list[Element] = []
    for x in __element_pattern.split(string):
        if x:
            if x[0] == "\x02" and x[-1] == "\x03":
                index, class_name = x[1:-1].split("_")
                if mapping[index].__class__.__name__ != class_name:
                    raise ValueError("Validation failed: not matching element type!")
                elements.append(mapping[index])
            else:
                elements.append(text(x))
    return chain(elements)
