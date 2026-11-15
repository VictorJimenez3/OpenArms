"""Conservative text constraints on a proposed route, not a motion planner."""
from __future__ import annotations

import re


VESSEL = r'(?:(?:the\s+)?(?:station|dock|cup|beaker|container|donor|receiver|vessel)\s+(?:at\s+)?)?'
RETURN_CLAUSE = re.compile(
    r'\b(?:return|leave|put|place|set|keep)\s+(?:the\s+)?(?:it|beaker|donor(?:\s+(?:cup|vessel))?|(?:(?:source|sample)\s+)?(?:cup|vessel))'
    r'\s+(?:back\s+)?(?:to|at|on)\s+(?:(?:the\s+)?(?:station|dock)\s+)?(?P<label>[a-z])\b', re.I)
# "bring it back to A", "then back to A": a return of the donor, not a pour destination.
BACK_CLAUSE = re.compile(
    r'\b(?:(?:bring|move|take|carry|get)\s+(?:the\s+)?(?:it|beaker|donor|cup|vessel)\s+)?(?<!pour )back\s+'
    r'(?:to|at|on|onto)\s+(?:(?:the\s+)?(?:station|dock|mark)\s+)?(?P<label>[a-z])\b', re.I)
NEGATIVE_ROUTE = re.compile(
    r'\bnot\s+(?:from\s+)?' + VESSEL + r'(?P<source>[a-z])\s+'
    r'(?:into|to|onto|in|->)\s+' + VESSEL + r'(?P<into>[a-z])\b', re.I)
DIRECTION = re.compile(
    r'\b(?P<direction>from|onto|into|to)\s+' + VESSEL +
    r'(?P<label>[a-z])\b(?=\s+(?:into|to|then|and|please|again|once|but|not)\b|\s*[,.;!?]|\s*$)', re.I)
# A source named straight after the verb ("pour B into C") has no "from" for WATER_ROUTE to see.
VERB_ROUTE = re.compile(
    r'\b(?:pour|tip|empty|decant|transfer|add)\s+(?:the\s+)?' + VESSEL +
    r'(?P<source>[a-z])\s+(?:onto|into|to|in)\s+' + VESSEL + r'(?P<into>[a-z])\b', re.I)
CONTENTS_SOURCE = re.compile(
    r'\b(?:contents|liquid|stuff)\s+(?:in|of)\s+' + VESSEL + r'(?P<label>[a-z])\b', re.I)
SHORT_ROUTE = re.compile(r'\b(?P<source>[a-z])\s*(?:-\s*to\s*-|->|\u2192)\s*(?P<into>[a-z])\b', re.I)
ROLE_AFTER = re.compile(
    r'\b' + VESSEL + r'(?P<label>[a-z])\s+(?:as|is)\s+(?:the\s+)?'
    r'(?P<role>source|donor|destination|receiver)\b', re.I)
ROLE_BEFORE = re.compile(
    r'\b(?P<role>source|donor|destination|receiver)(?:\s+(?:is|should be|will be))?'
    r'\s*[:=]?\s+' + VESSEL + r'(?P<label>[a-z])\b', re.I)
UNRESOLVED_NEGATION = re.compile(r"\b(?:not|never|don't|dont|without|except|unless|cannot|can't)\b", re.I)


def positive_pour_request(text, source, into):
    """Check explicit constraints against the proposal; leave unknown prose to the expert.

    Only a fully spelled-out negated route is separated from the positive
    instruction. Unresolved negation is not discarded or treated as consent.
    Station IDs come from the proposed action, never from this parser.
    """
    text = text.replace('\u2019', "'")
    forbidden = set()

    def negative(match):
        forbidden.add((match['source'].upper(), match['into'].upper()))
        return ' '

    positive = NEGATIVE_ROUTE.sub(negative, text)
    if not positive.strip(' ,.;!?') or UNRESOLVED_NEGATION.search(positive):
        raise ValueError('Clarify the positive action; no partial action was approved.')
    if (source, into) in forbidden:
        raise ValueError('The proposed route is explicitly negated; no pour was approved.')
    route_text = BACK_CLAUSE.sub('', RETURN_CLAUSE.sub('', positive))
    sources, destinations = set(), set()
    for match in DIRECTION.finditer(route_text):
        (sources if match['direction'].lower() == 'from' else destinations).add(match['label'].upper())
    sources.update(match['label'].upper() for match in CONTENTS_SOURCE.finditer(route_text))
    for pattern in (SHORT_ROUTE, VERB_ROUTE):
        for match in pattern.finditer(route_text):
            sources.add(match['source'].upper())
            destinations.add(match['into'].upper())
    for pattern in (ROLE_AFTER, ROLE_BEFORE):
        for match in pattern.finditer(route_text):
            (sources if match['role'].lower() in ('source', 'donor') else destinations).add(match['label'].upper())
    if forbidden and not (sources or destinations):
        raise ValueError('Specify the positive source and destination before proposing a pour.')
    if sources - {source}:
        raise ValueError(f'This setup can only pour from {source}. No pour was approved.')
    if destinations - {into}:
        raise ValueError(f'This setup can only pour into {into}. No pour was approved.')
    return positive
