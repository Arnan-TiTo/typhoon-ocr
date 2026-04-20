"""
Thai OCR Text Corrector
========================
Rule-based correction engine for Thai OCR errors.
No AI/GPU needed - uses dictionary mappings + character-level rules.

Architecture:
  Step 1: Direct mapping lookup (ocr_corrections.json)
  Step 2: Rule-based fallback (vowel swap, tone mark fix, etc.)
  Step 3: Return original if no correction found
"""
import json
import os
import re
import unicodedata

# ---------------------------------------------------------------------------
# Thai character classification
# ---------------------------------------------------------------------------

# Thai consonants (พยัญชนะ)
THAI_CONSONANTS = set("กขฃคฅฆงจฉชซฌญฎฏฐฑฒณดตถทธนบปผฝพฟภมยรลวศษสหฬอฮ")

# Thai vowels above/below (สระบน/ล่าง)
THAI_VOWELS_ABOVE = set("ิีึืั็")  # above consonant
THAI_VOWELS_BELOW = set("ุู")       # below consonant

# Thai tone marks (วรรณยุกต์)
THAI_TONE_MARKS = set("่้๊๋")

# Thai special marks
THAI_SPECIAL = set("์ํ็ๆฯ")

# All above-consonant marks (สระบน + วรรณยุกต์ + การันต์)
THAI_ABOVE_MARKS = THAI_VOWELS_ABOVE | THAI_TONE_MARKS | {"์"}

# Leading vowels (สระหน้า)
THAI_LEADING_VOWELS = set("เแโใไ")

# Following vowels (สระหลัง)
THAI_FOLLOWING_VOWELS = set("ะาำ")


def classify_char(ch):
    """Classify a Thai character."""
    if ch in THAI_CONSONANTS:
        return "consonant"
    if ch in THAI_VOWELS_ABOVE:
        return "vowel_above"
    if ch in THAI_VOWELS_BELOW:
        return "vowel_below"
    if ch in THAI_TONE_MARKS:
        return "tone"
    if ch in THAI_LEADING_VOWELS:
        return "vowel_leading"
    if ch in THAI_FOLLOWING_VOWELS:
        return "vowel_following"
    if ch == "์":
        return "cancellation"  # การันต์
    if ch == "ํ":
        return "nikhahit"
    return "other"


# ---------------------------------------------------------------------------
# Rule-based correction functions
# ---------------------------------------------------------------------------

def rule_swap_vowel_ui(word):
    """สลับสระ -ุ กับ -ี  (เช่น บรีุ → บุรี, ชลบรีุ → ชลบุรี)"""
    results = []
    chars = list(word)
    for i in range(len(chars) - 1):
        if chars[i] == "ุ" and chars[i + 1] == "ี":
            new = chars.copy()
            new[i], new[i + 1] = new[i + 1], new[i]
            results.append("".join(new))
        elif chars[i] == "ี" and chars[i + 1] == "ุ":
            new = chars.copy()
            new[i], new[i + 1] = new[i + 1], new[i]
            results.append("".join(new))
    return results


def rule_swap_vowel_ia(word):
    """สลับสระ -ิ กับ ตัวสะกด (เช่น ครมี → ครีม, สนิคา้ → สินค้า)"""
    results = []
    chars = list(word)
    for i in range(len(chars) - 1):
        if chars[i] in THAI_CONSONANTS and i + 1 < len(chars) and chars[i + 1] == "ี":
            # Try swapping consonant and ี
            if i + 2 <= len(chars):
                new = chars.copy()
                new[i], new[i + 1] = new[i + 1], new[i]
                results.append("".join(new))
    return results


def rule_swap_sara_ang(word):
    """สลับ -ั กับตัวสะกด (เช่น หนงั → หนัง, หวงั → หวัง)"""
    results = []
    chars = list(word)
    for i in range(len(chars) - 1):
        if chars[i] in THAI_CONSONANTS and chars[i + 1] == "ั":
            # already correct order: consonant + sara-an
            pass
        elif chars[i] in THAI_CONSONANTS and i + 1 < len(chars):
            if i + 2 < len(chars) and chars[i + 2] == "ั":
                # consonant1 + consonant2 + sara-an → consonant1 + sara-an + consonant2
                new = chars.copy()
                new[i + 1], new[i + 2] = new[i + 2], new[i + 1]
                results.append("".join(new))
    # Pattern: ง + ั at end → ั + ง
    for i in range(len(chars) - 1):
        if chars[i] in THAI_CONSONANTS and chars[i + 1] == "ั":
            pass
        if i > 0 and chars[i] in THAI_CONSONANTS and chars[i - 1] not in THAI_VOWELS_ABOVE | THAI_VOWELS_BELOW:
            if i + 1 < len(chars) and chars[i + 1] == "ั":
                pass  # Already correct
    # Simple pattern: last two chars are consonant + ั
    if len(chars) >= 2 and chars[-1] == "ั" and chars[-2] in THAI_CONSONANTS:
        new = chars.copy()
        new[-1], new[-2] = new[-2], new[-1]
        results.append("".join(new))
    return results


def rule_swap_gu(word):
    """สลับ ง+ุ → ุ+ง (เช่น กรงุ → กรุง)"""
    results = []
    if "งุ" in word:
        results.append(word.replace("งุ", "ุง"))
    return results


def rule_fix_nikhahit(word):
    """แก้ ํ กับ ำ สลับ (เช่น ตําบล → ตำบล)"""
    results = []
    if "ํา" in word:
        results.append(word.replace("ํา", "ำ"))
    if "าํ" in word:
        results.append(word.replace("าํ", "ำ"))
    return results


def rule_remove_extra_marks(word):
    """ลบวรรณยุกต์/สระซ้อน (เช่น ผิ์ว → ผิว)"""
    results = []
    chars = list(word)
    # Find consecutive above-marks
    for i in range(len(chars) - 1):
        t1 = classify_char(chars[i])
        t2 = classify_char(chars[i + 1])
        if t1 in ("vowel_above", "tone", "cancellation") and t2 in ("vowel_above", "tone", "cancellation"):
            # Remove one of them
            new1 = chars[:i] + chars[i + 1:]
            new2 = chars[:i + 1] + chars[i + 2:]
            results.append("".join(new1))
            results.append("".join(new2))
    return results


def rule_remove_space(word):
    """ลบช่องว่างในคำ (เช่น เข ต → เขต)"""
    if " " in word and len(word.replace(" ", "")) <= 6:
        return [word.replace(" ", "")]
    return []


def rule_swap_leading_vowel(word):
    """สลับสระนำ -เ กับ -ิ (เช่น พเิชษฐ์ → พิเชษฐ์)"""
    results = []
    chars = list(word)
    for i in range(len(chars) - 1):
        if chars[i] in THAI_VOWELS_ABOVE and chars[i + 1] in THAI_LEADING_VOWELS:
            new = chars.copy()
            new[i], new[i + 1] = new[i + 1], new[i]
            results.append("".join(new))
    return results


def rule_insert_missing_vowel(word):
    """เติมสระที่หายไป (เช่น ครม → ครีม, ผวิ → ผิว, บรด → บริด)
    OCR sometimes drops vowel marks entirely."""
    results = []
    # Common above/below vowels that OCR drops
    missing_vowels = ["ิ", "ี", "ึ", "ื", "ั", "ุ", "ู"]
    chars = list(word)

    for i in range(len(chars)):
        if chars[i] in THAI_CONSONANTS:
            # Try inserting each vowel after this consonant
            for vowel in missing_vowels:
                new = chars[:i + 1] + [vowel] + chars[i + 1:]
                results.append("".join(new))
    return results


def rule_swap_consonant_vowel_general(word):
    """สลับพยัญชนะกับสระบน/ล่าง ทั่วไป (เช่น ผวิ → ผิว)"""
    results = []
    chars = list(word)
    all_vowels = THAI_VOWELS_ABOVE | THAI_VOWELS_BELOW
    for i in range(len(chars) - 1):
        if chars[i] in THAI_CONSONANTS and chars[i + 1] in all_vowels:
            # Try swapping consonant with the vowel before it
            pass
        elif chars[i] in all_vowels and chars[i + 1] in THAI_CONSONANTS:
            # vowel before consonant → swap them
            new = chars.copy()
            new[i], new[i + 1] = new[i + 1], new[i]
            results.append("".join(new))
        elif chars[i] in THAI_CONSONANTS and chars[i + 1] in THAI_CONSONANTS:
            # Two consonants - try inserting vowel between for the general swap
            pass
    return results


# All rules to try (order matters: safest first)
CORRECTION_RULES = [
    rule_fix_nikhahit,
    rule_swap_vowel_ui,
    rule_swap_sara_ang,
    rule_swap_gu,
    rule_swap_vowel_ia,
    rule_swap_consonant_vowel_general,
    rule_remove_extra_marks,
    rule_remove_space,
    rule_swap_leading_vowel,
    rule_insert_missing_vowel,  # Last: most speculative
]


# ---------------------------------------------------------------------------
# Main Corrector Class
# ---------------------------------------------------------------------------

class ThaiOCRCorrector:
    """Rule-based Thai OCR text corrector."""

    def __init__(self, corrections_path=None, dictionary_path=None):
        self.mapping = {}
        self.thai_words = set()
        self.auto_learn = True  # Auto-save discovered corrections

        # Load corrections JSON
        if corrections_path is None:
            corrections_path = os.path.join(
                os.path.dirname(__file__), "thai_dict", "ocr_corrections.json"
            )
        if os.path.exists(corrections_path):
            self._load_corrections(corrections_path)
            print(f"[corrector] Loaded {len(self.mapping)} mappings from {os.path.basename(corrections_path)}")

        # Load Thai dictionary (for rule validation + auto-learn)
        if dictionary_path is None:
            # Try words_th.txt first, then thai_dictionary.txt
            for fname in ["words_th.txt", "thai_dictionary.txt"]:
                candidate = os.path.join(
                    os.path.dirname(__file__), "thai_dict", fname
                )
                if os.path.exists(candidate):
                    dictionary_path = candidate
                    break

        if dictionary_path and os.path.exists(dictionary_path):
            self._load_dictionary(dictionary_path)
            print(f"[corrector] Loaded {len(self.thai_words)} words from {os.path.basename(dictionary_path)}")
            print(f"[corrector] Auto-learn: ENABLED (rules + dictionary validation)")
        else:
            # Try loading from pythainlp if available
            try:
                from pythainlp.corpus import thai_words as ptn_words
                self.thai_words = ptn_words()
                print(f"[corrector] Loaded {len(self.thai_words)} words from pythainlp")
            except ImportError:
                print("[corrector] No Thai dictionary found (auto-learn disabled)")

    def _load_corrections(self, path):
        """Load ocr_corrections.json."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data.get("mappings", []):
            self.mapping[item["ocr_text"]] = item["correct_text"]

    def _load_dictionary(self, path):
        """Load Thai word list."""
        with open(path, "r", encoding="utf-8") as f:
            self.thai_words = set(line.strip() for line in f if line.strip())

    def add_mapping(self, ocr_text, correct_text):
        """Add a correction mapping at runtime."""
        self.mapping[ocr_text] = correct_text

    def correct_word(self, word):
        """Correct a single word/phrase."""
        # Step 1: Direct mapping lookup
        if word in self.mapping:
            return self.mapping[word]

        # Step 2: Skip if word is already correct (in dictionary)
        if self.thai_words and word in self.thai_words:
            return word

        # Step 3: Try rule-based correction (ONLY with dictionary validation)
        if self.thai_words:
            for rule_fn in CORRECTION_RULES:
                candidates = rule_fn(word)
                for candidate in candidates:
                    if candidate in self.thai_words:
                        # Auto-learn: save this correction for future use
                        if self.auto_learn:
                            print(f"[auto-learn] '{word}' -> '{candidate}' (rule: {rule_fn.__name__})")
                            self.learn(word, candidate)
                        return candidate

        # Step 4: Fallback - return original
        return word

    @staticmethod
    def _is_thai(ch):
        """Check if a character is Thai."""
        return '\u0E01' <= ch <= '\u0E7F'

    def _tokenize_thai(self, text):
        """
        Corrective Thai tokenizer using dictionary + OCR rules.
        For each position, tries all segment lengths and:
        1. Checks if segment is a known word
        2. Checks if segment has a mapping
        3. Tries rules on segment → checks if result is a known word
        4. Validates that remaining text can also form valid words (lookahead)
        Returns list of (token, corrected_token) pairs.
        """
        if not self.thai_words:
            return [(text, self.correct_word(text))]

        results = []
        i = 0
        max_word_len = 30

        while i < len(text):
            # If not Thai char, collect non-Thai segment
            if not self._is_thai(text[i]):
                j = i
                while j < len(text) and not self._is_thai(text[j]):
                    j += 1
                seg = text[i:j]
                results.append((seg, seg))
                i = j
                continue

            # Try all possible segment lengths (longest first)
            # For each candidate, verify the remainder can also start with a valid word
            best_len = 0
            best_corrected = None

            for seg_len in range(min(max_word_len, len(text) - i), 0, -1):
                seg = text[i:i + seg_len]
                candidate = None

                # 1. Already a known word
                if seg in self.thai_words:
                    candidate = seg

                # 2. Has a direct mapping
                elif seg in self.mapping:
                    candidate = self.mapping[seg]

                # 3. Try rules on this segment
                elif seg_len >= 2:
                    for rule_fn in CORRECTION_RULES:
                        rule_candidates = rule_fn(seg)
                        for rc in rule_candidates:
                            if rc in self.thai_words:
                                candidate = rc
                                break
                        if candidate:
                            break

                if candidate:
                    # Lookahead: check that remainder can start with valid word
                    remainder = text[i + seg_len:]
                    if not remainder or not self._is_thai(remainder[0]) if remainder else True:
                        # No Thai remainder or end of text → accept
                        if candidate != seg and seg not in self.mapping:
                            if self.auto_learn:
                                print(f"[auto-learn] '{seg}' -> '{candidate}' (tokenizer)")
                                self.learn(seg, candidate)
                        best_len = seg_len
                        best_corrected = candidate
                        break
                    else:
                        # Check if remainder starts with a valid word / correctable text
                        can_continue = self._can_start_valid(remainder)
                        if can_continue:
                            if candidate != seg and seg not in self.mapping:
                                if self.auto_learn:
                                    print(f"[auto-learn] '{seg}' -> '{candidate}' (tokenizer)")
                                    self.learn(seg, candidate)
                            best_len = seg_len
                            best_corrected = candidate
                            break
                        # else: try shorter segment

            if best_len > 0:
                results.append((text[i:i + best_len], best_corrected))
                i += best_len
            else:
                # Single char fallback
                results.append((text[i], text[i]))
                i += 1

        return results

    def _can_start_valid(self, text, max_check=15):
        """Check if text can start with a valid word (for lookahead)."""
        if not text:
            return True
        if not self._is_thai(text[0]):
            return True  # non-Thai is always valid

        # Try finding a valid word start in the first few chars
        for end in range(min(max_check, len(text)), 0, -1):
            seg = text[:end]
            if seg in self.thai_words or seg in self.mapping:
                return True
            # Also try rules
            if end >= 2:
                for rule_fn in CORRECTION_RULES:
                    candidates = rule_fn(seg)
                    for c in candidates:
                        if c in self.thai_words:
                            return True
        return False

    def correct_text(self, text):
        """
        Correct entire text using mappings + rules + Thai tokenization.

        Strategy:
        1. Try full text mapping first
        2. Try phrase-level mappings (longest first, no double replace)
        3. Tokenize remaining Thai segments and apply word-level rules
        """
        # Step 1: Full text mapping
        if text in self.mapping:
            return self.mapping[text]

        # Step 2: Apply all direct mappings as substring replacements (longest first)
        corrected = text
        placeholders = {}
        sorted_mappings = sorted(self.mapping.items(), key=lambda x: len(x[0]), reverse=True)
        for idx, (wrong, right) in enumerate(sorted_mappings):
            if wrong in corrected:
                if right in text and wrong in right:
                    continue
                placeholder = f"\x01PH{idx}\x02"
                corrected = corrected.replace(wrong, placeholder)
                placeholders[placeholder] = right

        # Replace placeholders with correct text
        for placeholder, right in placeholders.items():
            corrected = corrected.replace(placeholder, right)

        # Step 3: Tokenize Thai segments and apply word-level rules
        # Split by spaces first, then tokenize each Thai segment
        parts = corrected.split(" ")
        result_parts = []
        for part in parts:
            if not part:
                result_parts.append(part)
                continue

            # Check if this part contains Thai characters
            has_thai = any(self._is_thai(c) for c in part)
            if has_thai and self.thai_words:
                # Corrective tokenize: returns (original, corrected) pairs
                token_pairs = self._tokenize_thai(part)
                result_parts.append("".join(corrected_tok for _, corrected_tok in token_pairs))
            else:
                result_parts.append(self.correct_word(part))

        return " ".join(result_parts)

    def detect_rules(self, ocr_text, correct_text):
        """
        Auto-detect which OCR error rules apply by comparing characters.
        Returns (error_type, list_of_rules_applied).
        """
        rules = []
        error_type = "unknown"

        ocr_chars = list(ocr_text)
        correct_chars = list(correct_text)

        # Check for space removal
        if " " in ocr_text and " " not in correct_text:
            rules.append("ลบ-ช่องว่าง")

        # Check for ํ/ำ swap
        if ("ํ" in ocr_text and "ำ" in correct_text) or ("าํ" in ocr_text):
            rules.append("ํ-กับ-ำสลับ")
            error_type = "character_swap"

        # Check for vowel swaps by comparing character sets
        ocr_vowels_above = [(i, c) for i, c in enumerate(ocr_chars) if c in THAI_VOWELS_ABOVE]
        cor_vowels_above = [(i, c) for i, c in enumerate(correct_chars) if c in THAI_VOWELS_ABOVE]

        # Check ุ/ี swap
        if "ุ" in ocr_text and "ี" in ocr_text:
            ocr_ui = "".join(c for c in ocr_text if c in "ุี")
            cor_ui = "".join(c for c in correct_text if c in "ุี")
            if ocr_ui != cor_ui:
                rules.append("ุ-กับ-ีสลับ")
                error_type = "vowel_swap"

        # Check ิ/ี swap or position
        ocr_i = [i for i, c in enumerate(ocr_chars) if c == "ิ"]
        cor_i = [i for i, c in enumerate(correct_chars) if c == "ิ"]
        if ocr_i != cor_i and len(ocr_i) == len(cor_i):
            rules.append("ิ-ผิดตำแหน่ง")
            error_type = "vowel_swap"

        # Check consonant + vowel swap (e.g. ครมี→ครีม, หนงั→หนัง)
        for vowel_char in ["ี", "ั", "ุ", "ู", "ิ"]:
            for i in range(len(ocr_chars) - 1):
                if ocr_chars[i] in THAI_CONSONANTS and ocr_chars[i + 1] == vowel_char:
                    # Check if in correct text, the vowel comes before this consonant  
                    consonant = ocr_chars[i]
                    for j in range(len(correct_chars) - 1):
                        if correct_chars[j] == vowel_char and j + 1 < len(correct_chars) and correct_chars[j + 1] == consonant:
                            rules.append(f"{consonant}-กับ-{vowel_char}สลับ")
                            error_type = "vowel_consonant_swap"
                            break

        # Check tone mark errors
        for tone in THAI_TONE_MARKS:
            if tone in ocr_text and tone in correct_text:
                ocr_pos = ocr_text.index(tone)
                cor_pos = correct_text.index(tone)
                if ocr_pos != cor_pos:
                    rules.append(f"ย้าย-วรรณยุกต์-{tone}")
                    error_type = "tone_mark_error"

        # Check extra marks (more marks in OCR than correct)
        ocr_mark_count = sum(1 for c in ocr_text if c in THAI_ABOVE_MARKS)
        cor_mark_count = sum(1 for c in correct_text if c in THAI_ABOVE_MARKS)
        if ocr_mark_count > cor_mark_count:
            rules.append("ลบ-วรรณยุกต์ซ้อน")
            if error_type == "unknown":
                error_type = "tone_removal"

        # Check missing leading vowel (e.g. ผ่ล้อม → ไผ่ล้อม)
        for lv in THAI_LEADING_VOWELS:
            if lv not in ocr_text and lv in correct_text:
                rules.append(f"เติม-สระ-{lv}")
                error_type = "missing_leading_vowel"

        # Check character position swap (ง+ุ → ุ+ง)
        if "งุ" in ocr_text and "ุง" in correct_text:
            rules.append("ง-กับ-ุสลับ")
            error_type = "character_swap"

        # Fallback: compare lengths
        if len(ocr_text) != len(correct_text) and not rules:
            if len(ocr_text) > len(correct_text):
                rules.append("ตัวอักษรเกิน")
            else:
                rules.append("ตัวอักษรขาด")
            error_type = "complex_error"

        # If still no specific rules found
        if not rules:
            if ocr_text != correct_text:
                rules.append("สลับ-ตำแหน่ง-อักษร")
                error_type = "complex_error"

        return error_type, rules

    def learn(self, ocr_text, correct_text):
        """
        Learn a new correction: auto-detect rules and save to JSON.
        Returns the new mapping entry.
        """
        # Auto-detect rules
        error_type, rules = self.detect_rules(ocr_text, correct_text)

        # Create new entry
        new_entry = {
            "ocr_text": ocr_text,
            "correct_text": correct_text,
            "type": error_type,
            "rules_applied": rules,
        }

        # Add to runtime mapping
        self.mapping[ocr_text] = correct_text

        # Save to JSON file
        self._save_to_json(new_entry)

        return new_entry

    def _save_to_json(self, new_entry):
        """Append a new entry to ocr_corrections.json."""
        json_path = os.path.join(
            os.path.dirname(__file__), "thai_dict", "ocr_corrections.json"
        )
        # Load existing data
        data = {"mappings": []}
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

        # Check for duplicates
        existing = {m["ocr_text"] for m in data.get("mappings", [])}
        if new_entry["ocr_text"] not in existing:
            data["mappings"].append(new_entry)

            # Save back
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)

            return True
        return False

    def reload(self):
        """Reload corrections from JSON file."""
        self.mapping = {}
        corrections_path = os.path.join(
            os.path.dirname(__file__), "thai_dict", "ocr_corrections.json"
        )
        if os.path.exists(corrections_path):
            self._load_corrections(corrections_path)
        return len(self.mapping)

    def get_stats(self):
        """Get corrector statistics."""
        return {
            "total_mappings": len(self.mapping),
            "dictionary_words": len(self.thai_words),
            "rules_count": len(CORRECTION_RULES),
        }


# ---------------------------------------------------------------------------
# Thai Address Formatter
# ---------------------------------------------------------------------------

# Thai address keywords for detection
_ADDR_KEYWORDS = [
    "เลขที่", "บ้านเลขที่", "หมู่ที่", "หมู่", "ม.",
    "ซอย", "ซ.", "ถนน", "ถ.",
    "ตำบล", "ต.", "แขวง",
    "อำเภอ", "อ.", "เขต",
    "จังหวัด", "จ.",
]


def format_thai_address(text):
    """
    จัดรูปแบบที่อยู่ไทยจาก OCR ที่ตัวเลขอยู่ท้ายข้อความ

    Pattern ที่รองรับ:
    1. "เลขที่หมู่ที่ตำบล... จังหวัด... 19/7 3"
       → "เลขที่ 19/7 หมู่ที่ 3 ตำบล..."

    2. "ตำบล... อำเภอ... จังหวัด... 12345 19/7 3"
       → "เลขที่ 19/7 หมู่ที่ 3 ตำบล... อำเภอ... จังหวัด... 12345"
    """
    # Pattern: text ends with numbers like "19/7 3" or "123 5"
    # Match: number_with_slash space single_digit at end
    m = re.search(
        r'^(.*?)'                          # prefix (address labels + names)
        r'\s+'                             # space
        r'(\d+(?:/\d+)?)'                  # house number (e.g. 19/7 or 123)
        r'\s+'                             # space
        r'(\d{1,2})'                       # moo number (1-2 digits)
        r'\s*$',                           # end
        text
    )

    if m:
        addr_part = m.group(1).strip()
        house_no = m.group(2)
        moo = m.group(3)

        # Clean up: remove "เลขที่" and "หมู่ที่" labels from addr_part
        # if they appear without values right after
        addr_clean = addr_part
        addr_clean = re.sub(r'^เลขที่\s*หมู่ที่\s*', '', addr_clean)
        addr_clean = re.sub(r'^บ้านเลขที่\s*หมู่ที่\s*', '', addr_clean)
        addr_clean = re.sub(r'^เลขที่\s*', '', addr_clean)
        addr_clean = re.sub(r'^หมู่ที่\s*', '', addr_clean)

        # Remove duplicate tambon (e.g. "ตำบลไผ่ล้อม, ตำบลไผ่ล้อม" → "ตำบลไผ่ล้อม")
        addr_clean = re.sub(
            r'(ตำบล\S+),?\s*ตำบล\S+',
            r'\1',
            addr_clean
        )
        addr_clean = re.sub(
            r'(แขวง\S+),?\s*แขวง\S+',
            r'\1',
            addr_clean
        )

        # Remove leading comma/space
        addr_clean = addr_clean.strip(", ")

        # Build formatted address
        result = f"เลขที่ {house_no} หมู่ที่ {moo} {addr_clean}"
        return result.strip()

    # Pattern 2: just trailing numbers without explicit labels
    # e.g. "ตำบลไผ่ล้อม อำเภอบางกระทุ่ม จังหวัดพิษณุโลก 65110 19/7 3"
    m2 = re.search(
        r'^(.*?)'                          # address text
        r'\s+(\d{5})'                      # postal code
        r'\s+(\d+(?:/\d+)?)'              # house number
        r'\s+(\d{1,2})'                    # moo
        r'\s*$',
        text
    )

    if m2:
        addr_part = m2.group(1).strip()
        postal = m2.group(2)
        house_no = m2.group(3)
        moo = m2.group(4)

        result = f"เลขที่ {house_no} หมู่ที่ {moo} {addr_part} {postal}"
        return result.strip()

    return text


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_corrector = None


def get_corrector():
    """Get or create the singleton corrector instance."""
    global _corrector
    if _corrector is None:
        _corrector = ThaiOCRCorrector()
    return _corrector


def correct_text(text):
    """Convenience function to correct text."""
    return get_corrector().correct_text(text)


def correct_word(word):
    """Convenience function to correct a word."""
    return get_corrector().correct_word(word)


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    corrector = ThaiOCRCorrector()

    test_cases = [
        ("หนงั", "หนัง"),
        ("ชลบรีุ", "ชลบุรี"),
        ("ครมี", "ครีม"),
        ("กรงุเทพม หานคร", "กรุงเทพมหานคร"),
        ("ตําบล", "ตำบล"),
        ("ครมีกนัแดดสตูรแพทยผิ์วหนงั", "ครีมกันแดดสูตรแพทย์ผิวหนัง"),
        ("จงัหวดัชลบรีุ", "จังหวัดชลบุรี"),
        ("สง่ฟรี", "ส่งฟรี"),
    ]

    print("\n=== Thai OCR Corrector Test ===\n")
    passed = 0
    for input_text, expected in test_cases:
        result = corrector.correct_text(input_text)
        status = "OK" if result == expected else "FAIL"
        if status == "OK":
            passed += 1
        print(f"  [{status}] '{input_text}' -> '{result}' (expected: '{expected}')")

    print(f"\n  Result: {passed}/{len(test_cases)} passed")
    print(f"  Stats: {corrector.get_stats()}")
