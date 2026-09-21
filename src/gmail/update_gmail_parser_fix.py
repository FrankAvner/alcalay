from pathlib import Path
import shutil
import sys
import py_compile


PROJECT_ROOT = Path.home() / "alcalay"
TARGET_FILE = PROJECT_ROOT / "src" / "gmail" / "gmail_parser.py"


def find_save_parsed_message_block(source: str):
    marker = "def save_parsed_message("
    start = source.find(marker)

    if start == -1:
        return None

    next_method = source.find(
        "\n    # =========================================================",
        start + len(marker),
    )

    if next_method == -1:
        return source[start:]

    return source[start:next_method]


def fix_values_block(block: str):
    values_marker = "VALUES ("
    values_start = block.find(values_marker)

    if values_start == -1:
        return None

    on_conflict_marker = "\n                    ON CONFLICT"
    on_conflict_start = block.find(
        on_conflict_marker,
        values_start,
    )

    if on_conflict_start == -1:
        return None

    values_end = on_conflict_start

    old_values = block[values_start:values_end]

    new_values = """VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        CURRENT_TIMESTAMP
                    )
"""

    new_block = (
        block[:values_start]
        + new_values
        + block[values_end:]
    )

    return old_values, new_block


def main():
    print("=" * 72)
    print("UPDATE GMAIL PARSER")
    print("=" * 72)

    if not TARGET_FILE.exists():
        print()
        print("[ERROR] File not found:")
        print(TARGET_FILE)
        sys.exit(1)

    print()
    print("[FILE]")
    print(TARGET_FILE)

    source = TARGET_FILE.read_text(
        encoding="utf-8"
    )

    method_block = find_save_parsed_message_block(
        source
    )

    if method_block is None:
        print()
        print("[ERROR] save_parsed_message() was not found.")
        print()
        print("[INFO] No changes were made.")
        sys.exit(2)

    result = fix_values_block(
        method_block
    )

    if result is None:
        print()
        print("[ERROR] Could not locate the VALUES block")
        print("inside save_parsed_message().")
        print()
        print("[INFO] No changes were made.")
        sys.exit(3)

    old_values, new_method_block = result

    if "CURRENT_TIMESTAMP" in old_values:
        print()
        print("[INFO] CURRENT_TIMESTAMP is already present")
        print("inside the INSERT VALUES block.")
        print()
        print("[INFO] No changes were made.")
        return

    updated_source = source.replace(
        method_block,
        new_method_block,
        1,
    )

    backup_file = TARGET_FILE.with_suffix(
        TARGET_FILE.suffix + ".before_updated_at_fix"
    )

    if not backup_file.exists():
        shutil.copy2(
            TARGET_FILE,
            backup_file,
        )
        print()
        print("[BACKUP]")
        print(backup_file)
    else:
        print()
        print("[BACKUP] Already exists:")
        print(backup_file)

    TARGET_FILE.write_text(
        updated_source,
        encoding="utf-8",
    )

    print()
    print("[UPDATED]")
    print("save_parsed_message()")

    print()
    print("[CHECK] Python compilation")

    try:
        py_compile.compile(
            str(TARGET_FILE),
            doraise=True,
        )
    except Exception as exc:
        print()
        print("[ERROR] Python compilation failed:")
        print(exc)

        print()
        print("[RESTORE] Restoring original file")

        shutil.copy2(
            backup_file,
            TARGET_FILE,
        )

        print("[RESTORED]")
        sys.exit(4)

    print("[OK] Python compilation successful.")

    print()
    print("[CHECK] SQL VALUES block")

    updated_source_check = TARGET_FILE.read_text(
        encoding="utf-8"
    )

    updated_method = find_save_parsed_message_block(
        updated_source_check
    )

    if updated_method is None:
        print("[ERROR] Could not re-read save_parsed_message().")
        sys.exit(5)

    updated_result = fix_values_block(
        updated_method
    )

    if updated_result is None:
        print("[ERROR] Could not verify VALUES block.")
        sys.exit(6)

    current_values = updated_result[0]

    if "CURRENT_TIMESTAMP" not in current_values:
        print("[ERROR] CURRENT_TIMESTAMP was not installed.")
        sys.exit(7)

    print("[OK] CURRENT_TIMESTAMP is present.")

    print()
    print("=" * 72)
    print("UPDATE COMPLETED")
    print("=" * 72)
    print()
    print("The INSERT now uses:")
    print()
    print("    28 Python parameters")
    print("    + CURRENT_TIMESTAMP for updated_at")
    print()
    print("Backup:")
    print(backup_file)


if __name__ == "__main__":
    main()
