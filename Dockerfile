FROM python:3.12-slim

# Install ffmpeg and system deps
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libopus-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

WORKDIR /app

# Copy dependency files first (layer caching)
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen

# Copy source
COPY bot.py ./

# Start the bot
CMD ["uv", "run", "python", "bot.py"]
