"""Standard ISO-4 and IEEE venue abbreviation engine for BibTeX space reduction."""

from __future__ import annotations

import re

VENUE_ABBREVIATIONS: dict[str, str] = {
    # Top AI/ML conferences
    "advances in neural information processing systems": "Proc. NeurIPS",
    "neural information processing systems": "Proc. NeurIPS",
    "proceedings of the international conference on machine learning": "Proc. ICML",
    "international conference on machine learning": "Proc. ICML",
    "international conference on learning representations": "Proc. ICLR",
    "proceedings of the aaai conference on artificial intelligence": "Proc. AAAI",
    "aaai conference on artificial intelligence": "Proc. AAAI",
    "international joint conference on artificial intelligence": "Proc. IJCAI",
    # Computer Vision
    "proceedings of the ieee/cvf conference on computer vision and pattern recognition": "Proc. IEEE/CVF CVPR",
    "ieee/cvf conference on computer vision and pattern recognition": "Proc. IEEE/CVF CVPR",
    "ieee conference on computer vision and pattern recognition": "Proc. IEEE CVPR",
    "proceedings of the european conference on computer vision": "Proc. ECCV",
    "european conference on computer vision": "Proc. ECCV",
    "ieee/cvf international conference on computer vision": "Proc. IEEE/CVF ICCV",
    "international conference on computer vision": "Proc. IEEE ICCV",
    # NLP / Speech
    "proceedings of the association for computational linguistics": "Proc. ACL",
    "association for computational linguistics": "Proc. ACL",
    "conference on empirical methods in natural language processing": "Proc. EMNLP",
    "north american chapter of the association for computational linguistics": "Proc. NAACL",
    "international conference on acoustics, speech and signal processing": "Proc. IEEE ICASSP",
    # Major Journals & Transactions
    "ieee transactions on pattern analysis and machine intelligence": "IEEE Trans. Pattern Anal. Mach. Intell.",
    "ieee transactions on neural networks and learning systems": "IEEE Trans. Neural Netw. Learn. Syst.",
    "ieee transactions on information theory": "IEEE Trans. Inf. Theory",
    "ieee transactions on signal processing": "IEEE Trans. Signal Process.",
    "ieee transactions on wireless communications": "IEEE Trans. Wireless Commun.",
    "ieee journal on selected areas in communications": "IEEE J. Sel. Areas Commun.",
    "acm transactions on graphics": "ACM Trans. Graph.",
    "journal of machine learning research": "J. Mach. Learn. Res.",
    "nature machine intelligence": "Nat. Mach. Intell.",
    "nature communications": "Nat. Commun.",
    "nature": "Nature",
    "science": "Science",
    "proceedings of the national academy of sciences": "Proc. Natl. Acad. Sci. U.S.A.",
    "communications of the acm": "Commun. ACM",
    "siam journal on computing": "SIAM J. Comput.",
    "siam journal on optimization": "SIAM J. Optim.",
}

RE_BOOKTITLE = re.compile(r"(booktitle\s*=\s*[\{\"])(.*?)([\}\"])", re.IGNORECASE)
RE_JOURNAL = re.compile(r"(journal\s*=\s*[\{\"])(.*?)([\}\"])", re.IGNORECASE)


def abbreviate_venue(venue_str: str) -> str:
    """Return the standardized abbreviation for a venue name, or original if unknown."""
    cleaned = venue_str.strip().lower()
    # Direct lookup
    if cleaned in VENUE_ABBREVIATIONS:
        return VENUE_ABBREVIATIONS[cleaned]

    # Prefix match (e.g. "Proceedings of the 38th International Conference on Machine Learning")
    for full_name, abbr in VENUE_ABBREVIATIONS.items():
        if full_name in cleaned:
            return abbr

    return venue_str


def abbreviate_bib_string(bib_str: str) -> tuple[str, int]:
    """
    Abbreviate booktitle and journal fields in a BibTeX string.
    Returns (abbreviated_bib, count_of_changes).
    """
    count = 0

    def repl_booktitle(m: re.Match) -> str:
        nonlocal count
        prefix, val, suffix = m.group(1), m.group(2), m.group(3)
        abbr = abbreviate_venue(val)
        if abbr != val:
            count += 1
            return f"{prefix}{abbr}{suffix}"
        return m.group(0)

    def repl_journal(m: re.Match) -> str:
        nonlocal count
        prefix, val, suffix = m.group(1), m.group(2), m.group(3)
        abbr = abbreviate_venue(val)
        if abbr != val:
            count += 1
            return f"{prefix}{abbr}{suffix}"
        return m.group(0)

    res = RE_BOOKTITLE.sub(repl_booktitle, bib_str)
    res = RE_JOURNAL.sub(repl_journal, res)
    return res, count
