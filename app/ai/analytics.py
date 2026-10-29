"""
Document Analytics Engine for Vellakshya AI Document Workspace.
Calculates lexical density, sentence/paragraph metrics, Flesch-Kincaid readability,
reading time estimates, stopword-filtered keyword frequencies, and n-gram phrase frequencies.
Runs strictly in-process with zero cloud network calls.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Optional

import fitz  # PyMuPDF

# Standard English stopwords (comprehensive list of closed-class function words)
STOPWORDS = frozenset(
    {
        "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
        "aren't", "as", "at", "be", "because", "been", "before", "being", "below", "between",
        "both", "but", "by", "can", "can't", "cannot", "could", "couldn't", "did", "didn't",
        "do", "does", "doesn't", "doing", "don't", "down", "during", "each", "few", "for",
        "from", "further", "had", "hadn't", "has", "hasn't", "have", "haven't", "having",
        "he", "he'd", "he'll", "he's", "her", "here", "here's", "hers", "herself", "him",
        "himself", "his", "how", "how's", "i", "i'd", "i'll", "i'm", "i've", "if", "in",
        "into", "is", "isn't", "it", "it's", "its", "itself", "let's", "me", "more", "most",
        "mustn't", "my", "myself", "no", "nor", "not", "of", "off", "on", "once", "only",
        "or", "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same",
        "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so", "some",
        "such", "than", "that", "that's", "the", "their", "theirs", "them", "themselves",
        "then", "there", "there's", "these", "they", "they'd", "they'll", "they're", "they've",
        "this", "those", "through", "to", "too", "under", "until", "up", "very", "was",
        "wasn't", "we", "we'd", "we'll", "we're", "we've", "were", "weren't", "what", "what's",
        "when", "when's", "where", "where's", "which", "while", "who", "who's", "whom", "why",
        "why's", "with", "won't", "would", "wouldn't", "you", "you'd", "you'll", "you're",
        "you've", "your", "yours", "yourself", "yourselves"
    }
)


def count_syllables_in_word(word: str) -> int:
    """
    Estimates syllable count using vowel clusters and phonetic suffix adjustments.
    """
    w = word.lower().strip()
    if not w:
        return 0
    # Strip non-alpha characters
    w = re.sub(r"[^a-z]", "", w)
    if not w:
        return 0
    if len(w) <= 3:
        return 1

    # Replace common suffixes that affect count
    if w.endswith("es") or w.endswith("ed"):
        # e.g. 'cared' -> 1 syllable, 'passes' -> 2 syllables
        if not re.search(r"[aeiouy]{2}(?:ed|es)$", w) and not re.search(r"[cdfgjklmnpqrstvwxz]es$", w):
            w = w[:-2]
    elif w.endswith("e") and not w.endswith("le"):
        w = w[:-1]

    # Count vowel groups
    vowel_runs = re.findall(r"[aeiouy]+", w)
    count = len(vowel_runs)
    return max(1, count)


def detect_language_simple(text: str) -> tuple[str, str]:
    """
    Detects language using characteristic stopword distributions.
    Returns (iso_code, display_name).
    """
    sample = text[:5000].lower()
    words = re.findall(r"\b[a-z\u00C0-\u017F]+\b", sample)
    if not words:
        return ("en", "English")

    word_set = set(words)
    lang_markers = {
        ("es", "Spanish"): {"de", "la", "el", "en", "y", "a", "los", "se", "del", "las", "por", "un", "para", "con"},
        ("fr", "French"): {"de", "la", "le", "et", "les", "des", "en", "un", "du", "une", "que", "est", "pour", "dans"},
        ("de", "German"): {"der", "die", "und", "in", "den", "von", "zu", "das", "mit", "sich", "des", "auf", "für", "ist"},
        ("it", "Italian"): {"di", "e", "il", "la", "che", "in", "per", "un", "del", "della", "non", "si", "da", "con"},
        ("pt", "Portuguese"): {"de", "a", "o", "que", "e", "do", "da", "em", "um", "para", "com", "não", "uma", "os"},
        ("en", "English"): {"the", "and", "is", "in", "to", "of", "that", "it", "with", "as", "for", "on", "was", "at"}
    }

    best_score = 0
    best_lang = ("en", "English")
    for lang, markers in lang_markers.items():
        score = len(word_set.intersection(markers))
        if score > best_score:
            best_score = score
            best_lang = lang

    return best_lang


def parse_page_range(range_str: Optional[str], total_pages: int) -> set[int]:
    """
    Parses strings like '1-3, 5, 8-10' into 1-based page indices.
    If range_str is empty, 'all', or None, returns all page indices.
    """
    if not range_str or range_str.strip().lower() in ("all", "*", ""):
        return set(range(1, total_pages + 1))

    pages: set[int] = set()
    parts = [p.strip() for p in range_str.split(",") if p.strip()]
    for p in parts:
        if "-" in p:
            sub = [s.strip() for s in p.split("-") if s.strip()]
            if len(sub) == 2 and sub[0].isdigit() and sub[1].isdigit():
                start, end = int(sub[0]), int(sub[1])
                for idx in range(max(1, start), min(total_pages, end) + 1):
                    pages.add(idx)
        elif p.isdigit():
            idx = int(p)
            if 1 <= idx <= total_pages:
                pages.add(idx)

    return pages or set(range(1, total_pages + 1))


def compute_readability(words: list[str], sentences: list[str]) -> dict[str, Any]:
    """
    Computes Flesch Reading Ease and Flesch-Kincaid Grade Level.
    """
    total_words = max(1, len(words))
    total_sentences = max(1, len(sentences))
    total_syllables = sum(count_syllables_in_word(w) for w in words) or total_words

    # Flesch Reading Ease
    # 206.835 - 1.015 * (words / sentences) - 84.6 * (syllables / words)
    fre = 206.835 - 1.015 * (total_words / total_sentences) - 84.6 * (total_syllables / total_words)
    fre = round(max(0.0, min(100.0, fre)), 1)

    # Flesch-Kincaid Grade Level
    # 0.39 * (words / sentences) + 11.8 * (syllables / words) - 15.59
    fkgl = 0.39 * (total_words / total_sentences) + 11.8 * (total_syllables / total_words) - 15.59
    fkgl = round(max(1.0, fkgl), 1)

    # Interpretation
    if fre >= 90.0:
        interpretation = "Very Easy (5th grade reading level)"
    elif fre >= 80.0:
        interpretation = "Easy (6th grade reading level)"
    elif fre >= 70.0:
        interpretation = "Fairly Easy (7th grade reading level)"
    elif fre >= 60.0:
        interpretation = "Standard (8th & 9th grade level)"
    elif fre >= 50.0:
        interpretation = "Fairly Difficult (10th to 12th grade level)"
    elif fre >= 30.0:
        interpretation = "Difficult (College level)"
    else:
        interpretation = "Very Difficult / Technical (Graduate level)"

    return {
        "flesch_reading_ease": fre,
        "flesch_kincaid_grade": fkgl,
        "interpretation": interpretation,
        "total_syllables": total_syllables,
        "avg_words_per_sentence": round(total_words / total_sentences, 1),
        "avg_syllables_per_word": round(total_syllables / total_words, 2),
    }


def compute_document_analytics(
    text: str,
    page_count: int = 1,
    filtered_page_count: Optional[int] = None,
) -> dict[str, Any]:
    """
    Computes complete statistical profile for input text.
    """
    char_count = len(text)
    char_count_no_spaces = len(re.sub(r"\s+", "", text))

    # Tokenize words
    words = re.findall(r"\b[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?\b", text)
    word_count = len(words)

    # Tokenize sentences (handles periods, exclamation, questions)
    raw_sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text.strip())
    sentences = [s.strip() for s in raw_sentences if len(s.strip()) > 3]
    sentence_count = len(sentences) or (1 if word_count > 0 else 0)

    # Tokenize paragraphs (double newline breaks or indents)
    raw_paras = re.split(r"\n\s*\n", text.strip())
    paragraphs = [p.strip() for p in raw_paras if p.strip()]
    paragraph_count = len(paragraphs) or (1 if word_count > 0 else 0)

    # Estimated reading time: 225 words per minute
    wpm = 225
    read_time_minutes = word_count / wpm
    read_time_seconds = int(read_time_minutes * 60)
    if read_time_seconds < 60:
        read_time_human = f"{max(1, read_time_seconds)} sec"
    else:
        mins = read_time_seconds // 60
        secs = read_time_seconds % 60
        read_time_human = f"{mins} min {secs} sec" if secs > 0 else f"{mins} min"

    # Stopword-filtered keywords (unigrams)
    clean_words = [w.lower() for w in words if len(w) > 2 and w.lower() not in STOPWORDS and not w.isdigit()]
    word_counter = Counter(clean_words)
    total_clean = max(1, len(clean_words))
    top_keywords = [
        {
            "word": word,
            "count": count,
            "frequency_percent": round((count / total_clean) * 100, 2),
        }
        for word, count in word_counter.most_common(15)
    ]

    # Phrase frequencies (bigrams and trigrams)
    bigrams = []
    for i in range(len(words) - 1):
        w1, w2 = words[i].lower(), words[i + 1].lower()
        if w1 not in STOPWORDS and w2 not in STOPWORDS and len(w1) > 2 and len(w2) > 2:
            bigrams.append(f"{w1} {w2}")
    bigram_counter = Counter(bigrams)

    trigrams = []
    for i in range(len(words) - 2):
        w1, w2, w3 = words[i].lower(), words[i + 1].lower(), words[i + 2].lower()
        # Allow connecting stopword in the middle e.g. "board of directors", "point of view"
        if w1 not in STOPWORDS and w3 not in STOPWORDS and len(w1) > 2 and len(w3) > 2:
            trigrams.append(f"{w1} {w2} {w3}")
    trigram_counter = Counter(trigrams)

    top_phrases = [
        {"phrase": phrase, "count": count, "type": "bigram"}
        for phrase, count in bigram_counter.most_common(8)
    ] + [
        {"phrase": phrase, "count": count, "type": "trigram"}
        for phrase, count in trigram_counter.most_common(4)
    ]
    top_phrases.sort(key=lambda x: x["count"], reverse=True)

    # Language detection
    lang_code, lang_name = detect_language_simple(text)

    # Readability
    readability = compute_readability(words, sentences)

    return {
        "page_count": page_count,
        "filtered_page_count": filtered_page_count or page_count,
        "word_count": word_count,
        "char_count": char_count,
        "char_count_excluding_spaces": char_count_no_spaces,
        "sentence_count": sentence_count,
        "paragraph_count": paragraph_count,
        "estimated_read_time_seconds": read_time_seconds,
        "estimated_read_time_human": read_time_human,
        "language_code": lang_code,
        "language_name": lang_name,
        "readability": readability,
        "top_keywords": top_keywords,
        "top_phrases": top_phrases[:10],
    }


def analyze_pdf_document(
    pdf_bytes: bytes,
    page_range: Optional[str] = None,
    selected_text: Optional[str] = None,
) -> dict[str, Any]:
    """
    Extracts text from PDF (with optional page range or selected text) and calculates analytics.
    """
    if selected_text and selected_text.strip():
        # User provided direct selection
        return compute_document_analytics(selected_text.strip(), page_count=1, filtered_page_count=1)

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)
    target_pages = parse_page_range(page_range, total_pages)

    extracted_chunks: list[str] = []
    for page_num in range(1, total_pages + 1):
        if page_num in target_pages:
            page = doc[page_num - 1]
            t = page.get_text("text")
            if t.strip():
                extracted_chunks.append(t.strip())

    full_text = "\n\n".join(extracted_chunks)
    doc.close()

    return compute_document_analytics(
        text=full_text,
        page_count=total_pages,
        filtered_page_count=len(target_pages),
    )
