"""
LaTeX and text parsing, named method extraction, and attribution gap detection.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class SentenceSpan:
    text: str
    line_number: int
    citations: list[str] = field(default_factory=list)
    raw_text: str = ""


# Curated directory of canonical methods, algorithms, and architectures that require attribution
CANONICAL_METHODS: dict[str, str] = {
    # Parameter-efficient fine-tuning
    "lora": "Low-Rank Adaptation",
    "low-rank adaptation": "Low-Rank Adaptation",
    "qlora": "QLoRA: Efficient Finetuning of Quantized LLMs",
    "adalora": "AdaLoRA: Adaptive Budget Allocation for Parameter-Efficient Fine-Tuning",
    "dora": "DoRA: Weight-Decomposed Low-Rank Adaptation",
    "prefix tuning": "Prefix-Tuning: Optimizing Continuous Prompts for Generation",
    "prompt tuning": "The Power of Scale for Parameter-Efficient Prompt Tuning",
    # Architectures
    "transformer": "Attention Is All You Need",
    "vision transformer": "An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale",
    "vit": "An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale",
    "swin transformer": "Swin Transformer: Hierarchical Vision Transformer using Shifted Windows",
    "bert": "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding",
    "roberta": "RoBERTa: A Robustly Optimized BERT Pretraining Approach",
    "llama": "LLaMA: Open and Efficient Foundation Language Models",
    "mistral": "Mistral 7B",
    "mamba": "Mamba: Linear-Time Sequence Modeling with Selective State Spaces",
    "flashattention": "FlashAttention: Fast and Memory-Efficient Exact Attention with IO-Awareness",
    "flashattention-2": "FlashAttention-2: Faster Attention with Better Parallelism and Work Partitioning",
    "resnet": "Deep Residual Learning for Image Recognition",
    "densenet": "Densely Connected Convolutional Networks",
    "unet": "U-Net: Convolutional Networks for Biomedical Image Segmentation",
    # Generative models & Diffusion
    "ddpm": "Denoising Diffusion Probabilistic Models",
    "ddim": "Denoising Diffusion Implicit Models",
    "diffusion models": "Deep Unsupervised Learning using Nonequilibrium Thermodynamics",
    "stable diffusion": "High-Resolution Image Synthesis with Latent Diffusion Models",
    "nerf": "NeRF: Representing Scenes as Neural Radiance Fields for View Synthesis",
    "3d gaussian splatting": "3D Gaussian Splatting for Real-Time Radiance Field Rendering",
    # Multimodal & Self-supervised
    "clip": "Learning Transferable Visual Models From Natural Language Supervision",
    "simclr": "A Simple Framework for Contrastive Learning of Visual Representations",
    "moco": "Momentum Contrast for Unsupervised Visual Representation Learning",
    "infonce": "Representation Learning with Contrastive Predictive Coding",
    "byol": "Bootstrap Your Own Latent: A New Approach to Self-Supervised Learning",
    "barlow twins": "Barlow Twins: Self-Supervised Learning via Redundancy Reduction",
    # Optimizers & Components
    "adamw": "Decoupled Weight Decay Regularization",
    "adam optimizer": "Adam: A Method for Stochastic Optimization",
    "lion optimizer": "Symbolic Discovery of Optimization Algorithms",
    "rmsnorm": "Root Mean Square Layer Normalization",
    "rotary position embedding": "RoFormer: Enhanced Transformer with Rotary Position Embedding",
    "rope": "RoFormer: Enhanced Transformer with Rotary Position Embedding",
    "alibi": "Train Short, Test Long: Attention with Linear Biases Enables Input Length Extrapolation",
    # RL & Alignment
    "ppo": "Proximal Policy Optimization Algorithms",
    "dpo": "Direct Preference Optimization: Your Language Model is Secretly a Reward Model",
    "rlhf": "Training language models to follow instructions with human feedback",
    "trpo": "Trust Region Policy Optimization",
    "dqn": "Playing Atari with Deep Reinforcement Learning",
    "sac": "Soft Actor-Critic: Off-Policy Maximum Entropy Deep Reinforcement Learning with a Stochastic Actor",
    # Classical clustering & tree algorithms
    "dbscan": "A Density-Based Algorithm for Discovering Clusters in Large Spatial Databases with Noise",
    "hdbscan": "Density-Based Clustering Based on Hierarchical Density Estimates",
    "t-sne": "Visualizing Data using t-SNE",
    "umap": "UMAP: Uniform Manifold Approximation and Projection for Dimension Reduction",
    "xgboost": "XGBoost: A Scalable Tree Boosting System",
    "lightgbm": "LightGBM: A Highly Efficient Gradient Boosting Decision Tree",
    "catboost": "CatBoost: unbiased boosting with categorical features",
}

# Concepts considered common knowledge in computational and physical sciences (no citation required)
COMMON_KNOWLEDGE: set[str] = {
    "gradient descent",
    "stochastic gradient descent",
    "backpropagation",
    "fourier transform",
    "fast fourier transform",
    "fft",
    "cross entropy",
    "mean squared error",
    "mse",
    "sigmoid",
    "sigmoid function",
    "relu",
    "softmax",
    "linear regression",
    "logistic regression",
    "principal component analysis",
    "pca",
    "k-means",
    "k-means clustering",
    "support vector machine",
    "svm",
    "monte carlo",
    "newton's method",
    "bayes rule",
    "markov chain",
    "gaussian distribution",
    "normal distribution",
    "poisson distribution",
    "central limit theorem",
    "convolutional neural network",
    "cnn",
    "deep neural network",
    "dnn",
    "loss function",
    "learning rate",
    "overfitting",
    "underfitting",
    "hyperparameter",
    "cross validation",
    "data augmentation",
    "regularization",
    "weight decay",
}

# Hallmarks of AI-generated or informal online blog prose
INFORMAL_AND_AI_HALLMARKS: set[str] = {
    "delve",
    "delving",
    "testament",
    "tapestry",
    "pivotal",
    "beacon",
    "groundbreaking",
    "game-changer",
    "it is crucial to note",
    "it is worth noting",
    "in this tutorial",
    "in this blog post",
    "let's dive into",
    "let's explore",
    "check out our github",
    "in today's digital era",
    "in the ever-evolving landscape",
    "fosters a seamless",
}


def strip_latex_comments(content: str) -> str:
    """Strip LaTeX comments while preserving newlines and line counts."""
    lines = content.splitlines(keepends=True)
    cleaned = []
    for line in lines:
        # Match % not preceded by \
        m = re.search(r"(?<!\\)%", line)
        if m:
            cleaned.append(line[: m.start()] + "\n")
        else:
            cleaned.append(line)
    return "".join(cleaned)


def mask_latex_math(content: str) -> str:
    """Mask display and inline math environments to prevent false text matching."""
    # Mask display environments
    display_envs = [
        r"\\begin\{equation\*?\}.*?\\end\{equation\*?\}",
        r"\\begin\{align\*?\}.*?\\end\{align\*?\}",
        r"\\begin\{gather\*?\}.*?\\end\{gather\*?\}",
        r"\\begin\{multline\*?\}.*?\\end\{multline\*?\}",
        r"\\\[.*?\\\]",
        r"\$\$.*?\$\$",
    ]
    for env in display_envs:
        content = re.sub(
            env,
            lambda m: "\n" * m.group(0).count("\n"),
            content,
            flags=re.DOTALL,
        )

    # Mask inline math $...$ (single line)
    content = re.sub(r"(?<!\\)\$.*?(?<!\\)\$", " [MATH] ", content)
    return content


def extract_citations_from_span(text: str) -> list[str]:
    """Extract citation keys from standard LaTeX cite commands and numeric brackets."""
    citations: list[str] = []
    # LaTeX cite commands: \cite{key1,key2}, \citep[...]{key}
    latex_cites = re.findall(
        r"\\(?:cite|citep|citet|citeauthor|parencite|textcite)(?:\[[^\]]*\])*\{([^}]+)\}",
        text,
    )
    for c_group in latex_cites:
        for k in c_group.split(","):
            cleaned_k = k.strip()
            if cleaned_k:
                citations.append(cleaned_k)

    # Numeric style [1], [1, 2], [1-3]
    bracket_cites = re.findall(r"\[(\d+(?:\s*,\s*\d+)*)\]", text)
    for b in bracket_cites:
        citations.append(b.strip())

    return citations


def split_into_sentence_spans(content: str) -> list[SentenceSpan]:
    """Parse text into sentence spans tracking 1-based line numbers and local citations."""
    cleaned = strip_latex_comments(content)
    masked = mask_latex_math(cleaned)
    lines = masked.splitlines()

    spans: list[SentenceSpan] = []
    current_sentence: list[str] = []
    start_line = 1

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            if current_sentence:
                full_sent = " ".join(current_sentence).strip()
                if len(full_sent) > 5:
                    cites = extract_citations_from_span(full_sent)
                    spans.append(SentenceSpan(text=full_sent, line_number=start_line, citations=cites))
                current_sentence = []
            continue

        if not current_sentence:
            start_line = idx

        # Sentence boundary detection
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\\])", stripped)
        for i, part in enumerate(parts):
            if i == 0:
                current_sentence.append(part)
            else:
                full_sent = " ".join(current_sentence).strip()
                if len(full_sent) > 5:
                    cites = extract_citations_from_span(full_sent)
                    spans.append(SentenceSpan(text=full_sent, line_number=start_line, citations=cites))
                current_sentence = [part]
                start_line = idx

    if current_sentence:
        full_sent = " ".join(current_sentence).strip()
        if len(full_sent) > 5:
            cites = extract_citations_from_span(full_sent)
            spans.append(SentenceSpan(text=full_sent, line_number=start_line, citations=cites))

    return spans


def extract_potential_methods(text: str) -> list[tuple[str, str]]:
    """
    Extract recognized methods and heuristics from a sentence.
    Returns a list of (entity_name, canonical_query).
    """
    found: list[tuple[str, str]] = []
    lower_text = text.lower()

    # 1. Exact match against curated canonical methods dictionary
    for term, canonical_title in CANONICAL_METHODS.items():
        # Match as whole word or acronym
        pattern = r"\b" + re.escape(term) + r"\b"
        if re.search(pattern, lower_text):
            found.append((term, canonical_title))

    # 2. Heuristic extraction of capitalized named constructs
    # Matches patterns like 'Contrastive Divergence algorithm', 'Focal Loss function'
    heuristic_pattern = re.findall(
        r"\b([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*\s+(?:algorithm|architecture|mechanism|loss|framework|network|method|benchmark|protocol))\b",
        text,
    )
    for h in heuristic_pattern:
        h_clean = h.strip()
        h_lower = h_clean.lower()
        # Exclude common knowledge
        if h_lower in COMMON_KNOWLEDGE:
            continue
        # Exclude if already matched in exact list
        if any(h_lower in term for term, _ in found):
            continue
        found.append((h_clean, h_clean))

    return found


def detect_informal_ai_tropes(text: str) -> list[str]:
    """Detect presence of AI slop or informal blog phrasing."""
    lower = text.lower()
    matches = []
    for trope in INFORMAL_AND_AI_HALLMARKS:
        if re.search(r"\b" + re.escape(trope) + r"\b", lower):
            matches.append(trope)
    return matches
