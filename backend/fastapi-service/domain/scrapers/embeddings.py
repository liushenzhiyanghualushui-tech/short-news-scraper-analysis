from typing import List, Optional

import numpy as np

try:
    import torch
    import torch.nn.functional as F
    from transformers import AutoModel, AutoTokenizer
except Exception:
    torch = None
    F = None
    AutoModel = None
    AutoTokenizer = None


class LocalTransformerEmbedder:
    def __init__(
        self,
        model_name_or_path: str,
        *,
        device: Optional[str] = None,
        max_length: int = 256,
        batch_size: int = 16,
        normalize: bool = True
    ):
        if torch is None or AutoModel is None or AutoTokenizer is None:
            raise RuntimeError('transformers/torch 不可用')

        self.model_name_or_path = model_name_or_path
        self.max_length = int(max_length)
        self.batch_size = int(batch_size)
        self.normalize = bool(normalize)

        if device:
            self.device = torch.device(device)
        else:
            self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

        self.tokenizer = AutoTokenizer.from_pretrained(model_name_or_path)
        self.model = AutoModel.from_pretrained(model_name_or_path)
        self.model.eval()
        self.model.to(self.device)

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)

        all_vecs = []
        with torch.no_grad():
            for start in range(0, len(texts), self.batch_size):
                batch = texts[start:start + self.batch_size]
                inputs = self.tokenizer(
                    batch,
                    padding=True,
                    truncation=True,
                    max_length=self.max_length,
                    return_tensors='pt',
                )
                inputs = {k: v.to(self.device) for k, v in inputs.items()}
                outputs = self.model(**inputs)

                last_hidden = outputs.last_hidden_state
                attention = inputs.get('attention_mask')
                mask = attention.unsqueeze(-1).to(last_hidden.dtype)
                summed = (last_hidden * mask).sum(dim=1)
                denom = mask.sum(dim=1).clamp(min=1)
                vecs = summed / denom

                if self.normalize:
                    vecs = F.normalize(vecs, p=2, dim=1)

                all_vecs.append(vecs.detach().cpu().numpy())

        return np.concatenate(all_vecs, axis=0).astype(np.float32)
