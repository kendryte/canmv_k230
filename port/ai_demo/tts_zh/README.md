# Chinese TTS frontend

The frontend converts text to the input IDs used by the Chinese FastSpeech
encoder. It does not run the encoder, decoder or vocoder models.

## Processing stages

1. `text_normalization.cpp` expands numbers, dates, units and punctuation.
2. `zh_frontend.cpp` removes English letters and converts characters to initial
   and final phonemes using pinyin. It preserves the existing character-based
   pronunciation policy and grouping; word-level tone sandhi and erhua are not
   enabled by this path.
3. `tts_zh_preprocess.cpp` maps phonemes to IDs, packs 50-element encoder chunks,
   pads them with the mapping's `sp` ID (357 in the bundled mapping), and records
   each chunk's valid length. Initialization requires an `sp` entry. Unknown
   symbols and silence detection use that same ID. It omits a final chunk
   containing only padding/pause IDs, as the original frontend did.
4. `../ai_demo.c` converts owned native output to Python lists and translates
   native failures into Python exceptions.

`tts_zh_frontend_preprocess_safe()` returns an owned `TtsZhOutput` only on
success. `size == 50 * len_size`, and each entry in `len_data` is in `[1, 50]`.
Call `tts_zh_output_destroy()` to release the structure and both buffers;
`tts_zh_free_output()` adapts that operation to MicroPython cleanup callbacks.
Temporary output stays owned during allocation, so partially allocated output
is released on failure.

On failure the function returns `NULL` and sets a `TtsZhStatus`:

| Status | Python exception |
| --- | --- |
| `TTS_ZH_NO_PHONEMES` | `ValueError` |
| `TTS_ZH_INVALID_ARGUMENT` | `ValueError` |
| `TTS_ZH_OUT_OF_MEMORY` | `MemoryError` |
| `TTS_ZH_PREPROCESS_FAILED` | `RuntimeError` |

The older `tts_zh_frontend_preprocess()` entry point delegates to the same
implementation and returns `NULL` on failure. Neither entry point propagates
C++ exceptions across the C API. English-only text such as `ABCDEFG`, empty
text, and text filtered entirely to pauses must never reach tensor creation.
Both Python examples use `libs.TTSInput` to reject unusable text and requests
exceeding one 50-phoneme encoder chunk before tensor creation. These checks also
protect installations using older firmware. Deploy `resources/libs/TTSInput.py`
to `/sdcard/libs/` when updating the examples independently of the SD card image.

## Regression checks

From the CanMV repository root:

```sh
python3 -B unit_test/scripts/check_tts_frontend.py
python3 -B unit_test/scripts/check_tts_lazy_regex.py
```

The frontend fixtures were captured from commit `5e7d532` before the refactor.
The checks use production source and dictionaries with ASan/UBSan, validate
chunk boundaries and error statuses, and inject output allocation failures.
Board testing is still needed for model inference and audio playback. The
pinyin dictionaries remain shared through the existing global `pypinyin`
instance; this refactor does not introduce independent per-handle dictionaries.
