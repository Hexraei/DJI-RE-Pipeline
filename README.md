# DJI Firmware Automated Extraction & Decryption Pipeline

A robust, fully automated Python pipeline and GUI engine designed for the ingestion, extraction, decryption, structured organization, and comprehensive logging of DJI drone firmware containers.

---

## Capabilities

* **Dual-Mode Processing Engine:**
  * **Single File Processing:** Target individual firmware containers (`.tar`, `.bin`, `.zip`).
  * **Bulk Folder Processing:** Batch-process entire directories of firmware archives with dynamic pagination and dropdown selection mechanics.
* **Intelligent Ingestion & Discrepancy Parsing:** Automatically identifies file structure discrepancies, distinguishing between standard POSIX `.tar` archives and legacy xV4 binary firmware containers.
* **Automated Decryption & Inspection:** Scans extracted firmware modules (`.bin`, `.sig`) for `IM*H` cryptographic magic headers and automates payload decryption.
* **Structured Local Repository Management:** Automatically organizes ingested files into distinct local storage hierarchies (`Firmwares/Raw`, `Firmwares/Extracted`, and `Firmwares/Decrypted`).
* **Multi-Tiered CSV Logging:**
  * **Single File Logs:** Generates and appends dedicated log files per drone model (`Logs/Single File Processing/<model_name>.csv`).
  * **Bulk Batch Logs:** Generates timestamped master logs (`Logs/Bulk Folder Processing/<Date Time>.csv`) dynamically segmented into distinct per-model sections/sheets.

---

## Repository Structure & Embedded Tools

```text
DJI-RE-Pipeline/
├── main.py                # Master Tkinter GUI application & threading pipeline engine
├── requirements.txt       # Python package dependencies (pycryptodome)
├── .gitignore             # Git exclusion configuration for massive binaries & local logs
├── README.md              # Project documentation
└── tools/                 # Standalone extraction & decryption utilities
    ├── dji_xv4_fwcon.py   # Legacy xV4 binary container extractor
    └── dji_imah_fwsig.py  # IM*H firmware module verifier & decryptor
```

### Attribution & Citation
The standalone utilities housed within the `tools/` directory (`dji_xv4_fwcon.py` and `dji_imah_fwsig.py`) are originally authored by and sourced from the open-source **[dji-firmware-tools](https://github.com/o-gs/dji-firmware-tools)** repository by **o-gs**. Full attribution is given to the original repository maintainers for their foundational research in DJI firmware structure and cryptographic wrapping.

### Key Management & Decryption Notice (June 2026)
> [!IMPORTANT]
> This pipeline and its embedded standalone tools were officially packaged in **June 2026**. The underlying decryption utilities (`tools/dji_imah_fwsig.py`) house only the known cryptographic keys available up to this date. For future DJI firmware releases or newly introduced encryption wrappers, users must independently acquire and verify new decryption keys, or update the standalone tool scripts directly from the upstream repository.

---

## Dependencies

### 1. Python Packages
The pipeline and underlying tools rely on `pycryptodome` to execute cryptographic operations (AES decryption, Counter block management, SHA256 hashing, and RSA signature verification).

```bash
pip install -r requirements.txt
```

### 2. System Dependencies (Linux)
* **`zenity` (Optional but Recommended):** Proactively utilized by the GUI to render native Ubuntu/GNOME-style file and folder selection dialog windows. If `zenity` is absent, the application automatically falls back to standard Tkinter file dialogs.
  ```bash
  sudo apt-get install zenity
  ```

---

## Usage Instructions

### Launching the Engine
Ensure you are in the project root directory and execute the main pipeline script:

```bash
python3 main.py
```

### Operating Workflow
1. **Mode Selection:** Select either `Single File Processing` or `Bulk Folder Processing` from the Home screen.
2. **Container Ingestion:** Click `Browse File` (or `Browse Folder`) to select your target firmware container(s).
3. **Pipeline Execution:** Click `Execute Pipeline` (or `Execute Bulk Pipeline`). The GUI will automatically lock, indicate `Status: Processing`, and dispatch background worker threads to parse, unpack, decrypt, and log the firmware modules in real-time.
4. **Log Review:** Upon completion, review the real-time `Dashboard` table and `Logs` output directly within the split GUI, or inspect the generated CSV files located in the `Logs/` directory.
