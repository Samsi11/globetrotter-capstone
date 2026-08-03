# Use a modern Python runtime — must be 3.10+ for any future type-hint
# syntax like `dict | None`; 3.11-slim is a safe, small, stable choice.
FROM python:3.11-slim

# Set a working directory inside the container
WORKDIR /globetrotter

# Copy dependency file first to leverage Docker layer caching —
# this means `pip install` only re-runs when requirements.txt actually
# changes, not on every code edit, so rebuilds after this point are fast.
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application source code — this includes app/,
# templates/, static/ (css, js, images), and data/pois.json.
COPY . .

# Expose the port the app runs on
EXPOSE 5000

# Run the application as a module (NOT `python app/main.py`), so Python
# correctly resolves the `app` package and its internal imports.
CMD ["python", "-m", "app.main"]