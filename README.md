# ScanWise: Medical Barcode & Scanner Configuration Diagnostic Tool

ScanWise is a zero-install, standalone web application engineered for hospital IT site technicians to instantly test, decode, and diagnose barcode scanner configurations and barcode payloads in real time.

## Requirements

- Python 3.10+
- Flask & Waitress

## Running the Application

Because Python environments in this workspace are managed via **mise**, run the application server using:

```bash
mise exec python -- python run.py
```

Or if you have activated your Python virtual environment / mise environment:

```bash
python run.py
```

The diagnostic server will start at `http://0.0.0.0:5000`. Open your browser to test barcode scanner configurations.

## Running Tests

To run the automated test suite:

```bash
mise exec python -- pytest -v
```
