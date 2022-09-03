from graia.amnesia.message import Element, MessageChain, Text


def chain(elements: list[Element]) -> MessageChain:
    from graia.amnesia import message

    return message.__message_chain_class__(elements)


def text(string: str) -> Text:
    from graia.amnesia import message

    return message.__text_element_class__(string)
