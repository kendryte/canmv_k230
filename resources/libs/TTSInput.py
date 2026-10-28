"""Input validation shared by the Chinese TTS examples."""

import aidemo


class TTSInputError(ValueError):
    """Text that the fixed-size Chinese TTS encoder cannot synthesize."""


def validate_text(text):
    # Reject ASCII letters/whitespace before loading models or dictionaries.
    # Numbers, mixed Chinese text and symbols still use native normalization.
    if not isinstance(text, str):
        raise TypeError("TTS text must be a string")
    if not text.strip():
        raise TTSInputError("Please enter text")
    for char in text:
        if not ("A" <= char <= "Z" or "a" <= char <= "z" or char in " \t\r\n"):
            return
    raise TTSInputError("Enter Chinese text; English letters are ignored")


def preprocess_text(frontend, text):
    validate_text(text)
    try:
        data, lengths = aidemo.tts_zh_preprocess(frontend, text)
    except ValueError as error:
        raise TTSInputError(str(error))
    # Also protect boards running an older native frontend.
    if not data or not lengths:
        raise TTSInputError("Chinese TTS input contains no usable phonemes")
    if len(lengths) != 1 or len(data) != 50:
        raise TTSInputError("Text is too long for this sample; use at most 50 phonemes")
    if not 1 <= lengths[0] <= 50:
        raise TTSInputError("Invalid phoneme sequence length")
    return data, lengths
