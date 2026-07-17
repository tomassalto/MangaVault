"""Text chunking and smart sampling for LLM token budget optimization."""

import math


def estimate_tokens(text: str) -> int:
    """
    Estimate token count for a text string.
    Rough approximation: ~4 chars per token for English/Spanish.
    For more accuracy, use tiktoken, but this avoids the dependency load.
    """
    return max(1, len(text) // 4)


def chunk_text(text: str, num_chunks: int) -> list[str]:
    """
    Split text into N roughly equal-sized chunks.

    Tries to split at sentence boundaries (., !, ?) when possible.
    """
    if not text or num_chunks <= 0:
        return []

    if num_chunks == 1:
        return [text]

    # Split into sentences first
    sentences: list[str] = []
    current = ""
    for char in text:
        current += char
        if char in ".!?;" and len(current.strip()) > 5:
            sentences.append(current.strip())
            current = ""
    if current.strip():
        sentences.append(current.strip())

    if len(sentences) <= num_chunks:
        return sentences

    # Distribute sentences into chunks
    chunk_size = math.ceil(len(sentences) / num_chunks)
    chunks: list[str] = []
    for i in range(0, len(sentences), chunk_size):
        chunk = " ".join(sentences[i : i + chunk_size])
        if chunk:
            chunks.append(chunk)

    return chunks


def smart_sample(
    chunks: list[str],
    max_token_budget: int,
    strategy: str = "uniform",
) -> list[str]:
    """
    Select a subset of chunks that fits within the token budget.

    The budget is max_tokens / 2 (half for input, half for LLM output).

    Strategies:
    - 'uniform': evenly distributed across the text (beginning, middle, end)
    - 'weighted': heavier sampling at beginning and end (more context-rich)

    This ensures we maximize LLM context usage while minimizing content loss.
    """
    if not chunks:
        return []

    # Budget = half of max tokens (the other half is for LLM output)
    budget = max_token_budget // 2

    # Calculate tokens per chunk
    chunk_tokens = [(chunk, estimate_tokens(chunk)) for chunk in chunks]
    total_tokens = sum(t for _, t in chunk_tokens)

    # If everything fits, return all
    if total_tokens <= budget:
        return chunks

    # Calculate how many chunks we can afford
    avg_tokens_per_chunk = total_tokens / len(chunks)
    max_chunks = max(1, int(budget / avg_tokens_per_chunk))

    if max_chunks >= len(chunks):
        return chunks

    # Select chunks based on strategy
    selected_indices: list[int] = []

    if strategy == "weighted":
        # Heavier at start and end (where plot setup + conclusion are)
        # Pattern: first 30%, last 30%, then fill middle
        n = len(chunks)
        head = max(1, int(max_chunks * 0.35))
        tail = max(1, int(max_chunks * 0.35))
        middle = max(0, max_chunks - head - tail)

        # Head indices
        selected_indices.extend(range(min(head, n)))

        # Tail indices
        tail_start = max(head, n - tail)
        selected_indices.extend(range(tail_start, n))

        # Middle indices (evenly spaced)
        if middle > 0:
            middle_range = range(head, tail_start)
            if len(middle_range) > 0:
                step = max(1, len(middle_range) // (middle + 1))
                for i in range(middle):
                    idx = head + (i + 1) * step
                    if idx < tail_start:
                        selected_indices.append(idx)

    else:  # uniform
        # Evenly spaced across the full text
        step = len(chunks) / max_chunks
        for i in range(max_chunks):
            idx = min(int(i * step), len(chunks) - 1)
            selected_indices.append(idx)

    # Deduplicate and sort
    selected_indices = sorted(set(selected_indices))

    # Collect chunks, trimming if over budget
    selected: list[str] = []
    used_tokens = 0
    for idx in selected_indices:
        chunk = chunks[idx]
        tokens = estimate_tokens(chunk)
        if used_tokens + tokens > budget:
            # Trim the last chunk to fit
            remaining = budget - used_tokens
            chars_remaining = remaining * 4
            if chars_remaining > 20:
                selected.append(chunk[:chars_remaining] + "...")
            break
        selected.append(chunk)
        used_tokens += tokens

    return selected
