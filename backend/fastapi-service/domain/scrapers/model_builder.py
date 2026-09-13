"""
数据模型构建模块

提供短文本新闻分类模型的构建、训练、评估和优化功能：
1. 特征提取（TF-IDF、Word2Vec）
2. 模型训练（SVM、朴素贝叶斯、随机森林、CNN、RNN）
3. 性能评估（准确率、混淆矩阵、F1分数）
4. 模型优化

技术栈：Scikit-learn, TensorFlow/PyTorch, Numpy, Pandas, Matplotlib/Seaborn
"""

import os
import sys
import json
import pickle
import logging
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional, Any
from datetime import datetime
from collections import Counter
from types import SimpleNamespace

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('model_builder')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_PRETRAINED_ROOT = os.path.join(PROJECT_ROOT, 'saved_models', 'pretrained')
DEFAULT_BERT_MODEL_ID = 'bert-base-chinese'


def resolve_pretrained_model_path(pretrained_model: Optional[str] = None) -> str:
    """优先解析项目内预训练模型目录，避免重复走外网下载。"""
    requested = (pretrained_model or DEFAULT_BERT_MODEL_ID).strip()

    if os.path.isabs(requested):
        return requested

    if any(sep in requested for sep in ('/', '\\')):
        candidate = os.path.normpath(os.path.join(PROJECT_ROOT, requested))
        if os.path.isdir(candidate):
            return candidate
        return requested

    local_candidate = os.path.join(LOCAL_PRETRAINED_ROOT, requested)
    if os.path.isdir(local_candidate):
        return local_candidate

    return requested


def _coerce_scalar_metric(value, default: float = 0.0) -> float:
    """将数组或张量风格的指标值规范为 Python float。"""
    if value is None:
        return float(default)

    if isinstance(value, np.ndarray):
        if value.size == 0:
            return float(default)
        value = value.reshape(-1)[-1]
    elif isinstance(value, (list, tuple)):
        if not value:
            return float(default)
        value = value[-1]

    if hasattr(value, 'item'):
        try:
            value = value.item()
        except (TypeError, ValueError):
            pass

    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


class FGM:
    """Fast Gradient Method 对抗训练

    在 BERT word_embeddings 上施加梯度方向的微小扰动，
    让模型对输入的微小语义偏移更鲁棒，等效于隐式数据增强。
    仅作用于训练阶段，不影响推理。

    用法：
        fgm = FGM(model)
        loss.backward()          # 正常反向传播
        fgm.attack()             # 对 embedding 加扰动
        loss_adv = model(...)    # 对抗样本前向
        loss_adv.backward()      # 对抗梯度累积
        fgm.restore()            # 恢复原始 embedding
        optimizer.step()
    """

    def __init__(self, model, epsilon: float = 1.0, emb_name: str = 'word_embeddings'):
        self.model = model
        self.epsilon = epsilon
        self.emb_name = emb_name
        self.backup = {}

    def attack(self):
        """对 embedding 参数施加 epsilon 大小的梯度方向扰动"""
        for name, param in self.model.named_parameters():
            if self.emb_name in name and param.requires_grad and param.grad is not None:
                self.backup[name] = param.data.clone()
                norm = param.grad.data.norm(2)
                if norm != 0:
                    perturbation = self.epsilon * param.grad.data / norm
                    param.data.add_(perturbation)

    def restore(self):
        """恢复 embedding 参数到扰动前的状态"""
        for name, param in self.model.named_parameters():
            if name in self.backup:
                param.data = self.backup[name]
        self.backup = {}


class RuleClassifier:
    """规则分类器"""
    
    def __init__(self, rules: Dict[str, List[str]] = None):
        """
        初始化规则分类器
        
        Args:
            rules: 分类规则字典 {分类名: [关键词列表]}
        """
        self.rules = rules or {}
    
    def set_rules(self, rules: Dict[str, List[str]]):
        """设置规则"""
        self.rules = rules
    
    def predict(self, text: str) -> str:
        """
        根据规则预测分类
        
        Args:
            text: 输入文本
            
        Returns:
            分类名称 (如果未匹配到则返回 None)
        """
        if not text or not self.rules:
            return None
            
        # 统计每个分类的关键词命中数
        scores = {}
        for category, keywords in self.rules.items():
            count = 0
            for keyword in keywords:
                if keyword in text:
                    count += 1
            
            # 命中 >= 2 个关键词才算有效 (根据需求文档)
            if count >= 2:
                scores[category] = count
        
        if not scores:
            return None
            
        # 返回命中数最多的分类
        return max(scores.items(), key=lambda x: x[1])[0]
    
    def batch_predict(self, texts: List[str]) -> List[str]:
        """批量预测"""
        return [self.predict(text) for text in texts]


class TextClassifier:
    """文本分类器基类"""
    
    def __init__(self, model_name: str = 'classifier'):
        """
        初始化文本分类器
        
        Args:
            model_name: 模型名称，用于保存模型文件
        """
        self.model_name = model_name
        self.model = None
        self.vectorizer = None
        self.label_encoder = None
        self.is_trained = False
        
        # 模型配置
        self.config = {
            'vectorizer_method': 'tfidf',
            'max_features': 5000,
            'ngram_range': (1, 2),
            'model_type': 'svm',
        }
        
        # 新闻分类类别
        self.categories = [
            '政治', '经济', '体育', '娱乐', '科技', '教育',
            '军事', '国际', '社会', '文化', '财经', '汽车', '房产', '游戏'
        ]
    
    def set_categories(self, categories: List[str]):
        """设置分类类别"""
        self.categories = categories
    
    def set_config(self, config: Dict):
        """更新模型配置"""
        self.config.update(config)

    def is_ready(self) -> bool:
        """检查模型是否具备推理/评估所需的核心组件。"""
        return bool(
            self.is_trained and
            self.model is not None and
            self.vectorizer is not None and
            self.label_encoder is not None
        )

    def ensure_ready(self, action: str = '推理'):
        """在执行预测或评估前确保模型已完整加载。"""
        if not self.is_trained:
            raise ValueError("模型未训练")

        if not self.is_ready():
            raise ValueError(f"模型未正确加载，无法{action}。请重新训练并保存模型")
    
    # ==================== 特征提取 ====================
    
    def _create_vectorizer(self):
        """创建特征向量化器"""
        from sklearn.feature_extraction.text import TfidfVectorizer
        
        method = self.config.get('vectorizer_method', 'tfidf')
        max_features = self.config.get('max_features', 5000)
        ngram_range = self.config.get('ngram_range', (1, 2))
        
        if method == 'tfidf':
            self.vectorizer = TfidfVectorizer(
                max_features=max_features,
                ngram_range=ngram_range,
                token_pattern=r'(?u)\b\w+\b',
                min_df=2,
                max_df=0.95
            )
        else:
            from sklearn.feature_extraction.text import CountVectorizer
            self.vectorizer = CountVectorizer(
                max_features=max_features,
                ngram_range=ngram_range,
                token_pattern=r'(?u)\b\w+\b',
                min_df=2,
                max_df=0.95
            )
    
    def _encode_labels(self, labels: List[str]):
        """编码标签"""
        from sklearn.preprocessing import LabelEncoder
        
        self.label_encoder = LabelEncoder()
        encoded = self.label_encoder.fit_transform(labels)
        return encoded
    
    def extract_features(self, texts: List[str]) -> np.ndarray:
        """
        提取文本特征
        
        Args:
            texts: 文本列表
            
        Returns:
            特征矩阵
        """
        if self.vectorizer is None:
            self._create_vectorizer()
            self.vectorizer.fit(texts)
        
        features = self.vectorizer.transform(texts)
        return features.toarray()
    
    def get_feature_names(self) -> List[str]:
        """获取特征名称（词汇表）"""
        if self.vectorizer:
            return list(self.vectorizer.get_feature_names_out())
        return []

    def _build_metric_results(self, encoded_labels, predictions, sample_count: int) -> Dict:
        """统一构建评估结果，供不同模型实现复用。"""
        from sklearn.metrics import (
            accuracy_score, precision_score, recall_score, f1_score,
            classification_report, confusion_matrix
        )

        raw_classes = getattr(self.label_encoder, 'classes_', None)
        classes = list(raw_classes) if raw_classes is not None else []
        label_ids = list(range(len(classes))) if classes else None

        accuracy = accuracy_score(encoded_labels, predictions)
        precision = precision_score(
            encoded_labels,
            predictions,
            average='weighted',
            labels=label_ids,
            zero_division=0
        )
        recall = recall_score(
            encoded_labels,
            predictions,
            average='weighted',
            labels=label_ids,
            zero_division=0
        )
        f1 = f1_score(
            encoded_labels,
            predictions,
            average='weighted',
            labels=label_ids,
            zero_division=0
        )

        cm = confusion_matrix(encoded_labels, predictions, labels=label_ids)
        report = classification_report(
            encoded_labels,
            predictions,
            labels=label_ids,
            target_names=[str(c) for c in classes] if classes else None,
            output_dict=True,
            zero_division=0
        )

        return {
            'accuracy': round(float(accuracy), 4),
            'precision': round(float(precision), 4),
            'recall': round(float(recall), 4),
            'f1_score': round(float(f1), 4),
            'confusion_matrix': cm.tolist(),
            'classification_report': report,
            'test_samples': int(sample_count)
        }

    def _build_confusion_matrix_payload(self, encoded_labels, predictions) -> Dict:
        """统一构建混淆矩阵可视化数据。"""
        from sklearn.metrics import confusion_matrix

        raw_classes = getattr(self.label_encoder, 'classes_', None)
        classes = list(raw_classes) if raw_classes is not None else []
        label_ids = list(range(len(classes))) if classes else None

        cm = confusion_matrix(encoded_labels, predictions, labels=label_ids)
        return {
            'matrix': cm.tolist(),
            'labels': [str(c) for c in classes],
            'categories': self.categories
        }
    
    # ==================== 模型训练 ====================
    
    def _create_model(self):
        """创建分类模型"""
        model_type = self.config.get('model_type', 'svm')
        
        if model_type == 'svm':
            from sklearn.svm import SVC
            self.model = SVC(
                kernel='linear',
                C=1.0,
                probability=True,
                random_state=42
            )
        elif model_type == 'nb':
            from sklearn.naive_bayes import MultinomialNB
            self.model = MultinomialNB(alpha=0.1)
        elif model_type == 'rf':
            from sklearn.ensemble import RandomForestClassifier
            self.model = RandomForestClassifier(
                n_estimators=100,
                max_depth=20,
                random_state=42,
                n_jobs=-1
            )
        elif model_type == 'knn':
            from sklearn.neighbors import KNeighborsClassifier
            self.model = KNeighborsClassifier(n_neighbors=5)
        elif model_type == 'lr':
            from sklearn.linear_model import LogisticRegression
            self.model = LogisticRegression(
                max_iter=1000,
                random_state=42,
                n_jobs=-1
            )
        else:
            logger.warning(f"未知模型类型: {model_type}，使用默认 SVM")
            from sklearn.svm import SVC
            self.model = SVC(kernel='linear', probability=True, random_state=42)
    
    def train(self, texts: List[str], labels: List[str], callback=None) -> Dict:
        """
        训练模型
        
        Args:
            texts: 训练文本列表
            labels: 标签列表
            callback: 进度回调函数 callback(progress, message)
            
        Returns:
            训练结果字典
        """
        if not texts or not labels:
            raise ValueError("训练数据不能为空")
        
        if len(texts) != len(labels):
            raise ValueError("文本数量与标签数量不匹配")
        
        logger.info(f"开始训练模型，训练样本数: {len(texts)}")
        if callback:
            callback(10, "正在初始化...")
        
        try:
            # 1. 特征提取
            if callback:
                callback(20, "正在提取文本特征...")
            self._create_vectorizer()
            features = self.vectorizer.fit_transform(texts)
            logger.info(f"特征维度: {features.shape}")
            
            # 2. 标签编码
            if callback:
                callback(40, "正在处理标签编码...")
            encoded_labels = self._encode_labels(labels)
            
            # 3. 创建并训练模型
            if callback:
                callback(50, f"正在训练 {self.config.get('model_type', 'svm')} 模型...")
            self._create_model()
            self.model.fit(features, encoded_labels)
            
            self.is_trained = True
            
            # 4. 计算训练集准确率
            if callback:
                callback(90, "正在评估训练效果...")
            train_accuracy = self.model.score(features, encoded_labels)
            
            logger.info(f"模型训练完成，训练准确率: {train_accuracy:.4f}")
            if callback:
                callback(100, "训练完成")
            
            return {
                'success': True,
                'train_samples': len(texts),
                'feature_dim': int(features.shape[1]),
                'train_accuracy': float(train_accuracy),
                'model_type': self.config.get('model_type', 'svm'),
                'categories': list(self.label_encoder.classes_)
            }
            
        except Exception as e:
            logger.error(f"模型训练失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def predict(self, texts: List[str]) -> List[Dict]:
        """
        预测文本类别
        
        Args:
            texts: 待预测文本列表
            
        Returns:
            预测结果列表，每个元素包含 {'text', 'category', 'confidence'}
        """
        self.ensure_ready('预测')
        
        if isinstance(texts, str):
            texts = [texts]
        
        # 特征提取
        features = self.vectorizer.transform(texts)
        
        # 预测
        predictions = self.model.predict(features)
        
        # 获取概率（如果支持）
        try:
            probabilities = self.model.predict_proba(features)
            confidences = probabilities.max(axis=1)
        except Exception:
            confidences = [1.0] * len(predictions)
        
        # 转换标签
        categories = self.label_encoder.inverse_transform(predictions)
        
        results = []
        for text, category, confidence in zip(texts, categories, confidences):
            results.append({
                'text': text[:100] + '...' if len(text) > 100 else text,
                'category': category,
                'confidence': round(float(confidence), 4)
            })
        
        return results
    
    def predict_single(self, text: str) -> Dict:
        """预测单条文本"""
        results = self.predict([text])
        return results[0] if results else {'category': '未知', 'confidence': 0}
    
    # ==================== 模型评估 ====================
    
    def evaluate(self, texts: List[str], labels: List[str]) -> Dict:
        """
        评估模型性能
        
        Args:
            texts: 测试文本列表
            labels: 真实标签列表
            
        Returns:
            评估结果字典
        """
        self.ensure_ready('评估')
        
        # 特征提取
        features = self.vectorizer.transform(texts)
        
        # 标签编码
        encoded_labels = self.label_encoder.transform(labels)
        
        # 预测
        predictions = self.model.predict(features)
        
        results = self._build_metric_results(encoded_labels, predictions, len(texts))
        
        logger.info(f"模型评估完成，准确率: {results['accuracy']:.4f}")
        
        return results
    
    def get_confusion_matrix_data(self, texts: List[str], labels: List[str]) -> Dict:
        """
        获取混淆矩阵数据（用于可视化）
        
        Returns:
            混淆矩阵数据字典
        """
        self.ensure_ready('生成混淆矩阵')

        # 特征提取
        features = self.vectorizer.transform(texts)
        encoded_labels = self.label_encoder.transform(labels)
        predictions = self.model.predict(features)

        return self._build_confusion_matrix_payload(encoded_labels, predictions)
    
    # ==================== 模型保存与加载 ====================
    
    def save(self, filepath: str = None):
        """
        保存模型
        
        Args:
            filepath: 保存路径
        """
        if filepath is None:
            filepath = f'{self.model_name}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pkl'
        
        model_data = {
            'model': self.model,
            'vectorizer': self.vectorizer,
            'label_encoder': self.label_encoder,
            'config': self.config,
            'categories': self.categories,
            'is_trained': self.is_trained
        }
        
        with open(filepath, 'wb') as f:
            pickle.dump(model_data, f)
        
        logger.info(f"模型已保存到: {filepath}")
        return filepath
    
    def load(self, filepath: str):
        """
        加载模型
        
        Args:
            filepath: 模型文件路径
        """
        with open(filepath, 'rb') as f:
            model_data = pickle.load(f)
        
        self.model = model_data['model']
        self.vectorizer = model_data['vectorizer']
        self.label_encoder = model_data['label_encoder']
        self.config = model_data.get('config', {})
        self.categories = model_data.get('categories', self.categories)
        self.is_trained = model_data.get('is_trained', True)
        
        logger.info(f"模型已加载: {filepath}")
    
    # ==================== 模型优化 ====================
    
    def optimize_hyperparameters(self, texts: List[str], labels: List[str],
                                  param_grid: Dict = None, cv: int = 5) -> Dict:
        """
        超参数优化（使用网格搜索）
        
        Args:
            texts: 训练文本
            labels: 标签
            param_grid: 参数网格
            cv: 交叉验证折数
            
        Returns:
            优化结果
        """
        from sklearn.model_selection import GridSearchCV
        
        # 特征提取
        features = self.vectorizer.fit_transform(texts)
        encoded_labels = self._encode_labels(labels)
        
        # 默认参数网格
        if param_grid is None:
            param_grid = {
                'C': [0.1, 1, 10],
                'kernel': ['linear', 'rbf']
            }
        
        # 创建基础模型
        from sklearn.svm import SVC
        base_model = SVC(random_state=42)
        
        # 网格搜索
        grid_search = GridSearchCV(
            base_model, param_grid, cv=cv, scoring='accuracy', n_jobs=-1
        )
        grid_search.fit(features, encoded_labels)
        
        logger.info(f"最佳参数: {grid_search.best_params_}")
        logger.info(f"最佳交叉验证得分: {grid_search.best_score_:.4f}")
        
        return {
            'best_params': grid_search.best_params_,
            'best_cv_score': grid_search.best_score_,
            'cv_results': grid_search.cv_results_
        }
    
    def cross_validate(self, texts: List[str], labels: List[str], 
                      cv: int = 5) -> Dict:
        """
        交叉验证
        
        Args:
            texts: 文本列表
            labels: 标签列表
            cv: 折数
            
        Returns:
            交叉验证结果
        """
        from sklearn.model_selection import cross_val_score
        
        # 特征提取
        features = self.vectorizer.fit_transform(texts)
        encoded_labels = self._encode_labels(labels)
        
        # 交叉验证
        scores = cross_val_score(self.model, features, encoded_labels, cv=cv, scoring='accuracy')
        
        return {
            'cv_scores': scores.tolist(),
            'mean_accuracy': scores.mean(),
            'std_accuracy': scores.std()
        }


class DeepLearningClassifier(TextClassifier):
    """深度学习文本分类器（使用 Keras/TensorFlow）"""
    
    def __init__(self, model_name: str = 'dl_classifier'):
        super().__init__(model_name)
        self.keras_model = None
        self.max_sequence_length = 100
        self.embedding_dim = 128
        
    def _create_model(self):
        """创建深度学习模型"""
        try:
            import tensorflow as tf
            from tensorflow.keras.models import Sequential
            from tensorflow.keras.layers import (
                Dense, Dropout, Embedding, Conv1D, GlobalMaxPooling1D,
                LSTM, Bidirectional, Input
            )
            from tensorflow.keras.optimizers import Adam
        except ImportError:
            logger.error("TensorFlow 未安装，无法使用深度学习模型")
            return
        
        model_type = self.config.get('model_type', 'cnn')
        vocab_size = len(self.vectorizer.get_feature_names_out()) + 1
        
        if model_type == 'cnn':
            self.keras_model = Sequential([
                Embedding(vocab_size, self.embedding_dim, input_length=self.max_sequence_length),
                Conv1D(128, 5, activation='relu'),
                GlobalMaxPooling1D(),
                Dense(64, activation='relu'),
                Dropout(0.5),
                Dense(len(self.categories), activation='softmax')
            ])
        elif model_type == 'lstm':
            self.keras_model = Sequential([
                Embedding(vocab_size, self.embedding_dim, input_length=self.max_sequence_length),
                Bidirectional(LSTM(64)),
                Dropout(0.5),
                Dense(32, activation='relu'),
                Dense(len(self.categories), activation='softmax')
            ])
        else:
            # 默认 CNN
            self.keras_model = Sequential([
                Embedding(vocab_size, self.embedding_dim, input_length=self.max_sequence_length),
                Conv1D(128, 5, activation='relu'),
                GlobalMaxPooling1D(),
                Dense(64, activation='relu'),
                Dropout(0.5),
                Dense(len(self.categories), activation='softmax')
            ])
        
        learning_rate = float(self.config.get('learning_rate', 1e-3))
        self.keras_model.compile(
            optimizer=Adam(learning_rate=learning_rate),
            loss='sparse_categorical_crossentropy',
            metrics=['accuracy']
        )
        self.model = self.keras_model
        
        logger.info(f"深度学习模型创建完成，learning_rate={learning_rate:g}")

    def is_ready(self) -> bool:
        """检查深度学习模型是否具备推理/评估所需的核心组件。"""
        return bool(
            self.is_trained and
            self.keras_model is not None and
            self.vectorizer is not None and
            self.label_encoder is not None
        )
    
    def train(self, texts: List[str], labels: List[str], 
             epochs: int = 10, batch_size: int = 32, learning_rate: float = 1e-3, callback=None) -> Dict:
        """训练深度学习模型"""
        import tensorflow as tf
        from tensorflow.keras.callbacks import Callback
        
        # 进度回调
        class ProgressCallback(Callback):
            def __init__(self, outer_callback, total_epochs):
                self.outer_callback = outer_callback
                self.total_epochs = total_epochs
                self.current_epoch = 0
                self.total_batches = 0

            def on_epoch_begin(self, epoch, logs=None):
                self.current_epoch = epoch
                self.total_batches = int(self.params.get('steps') or 0)

            def on_train_batch_end(self, batch, logs=None):
                if not self.outer_callback:
                    return

                if self.total_batches <= 0:
                    return

                is_last_batch = (batch + 1) >= self.total_batches
                if batch % 10 != 0 and not is_last_batch:
                    return

                progress = 18 + int(
                    ((self.current_epoch + ((batch + 1) / self.total_batches)) / self.total_epochs) * 72
                )
                acc = _coerce_scalar_metric((logs or {}).get('accuracy', 0))
                self.outer_callback(
                    min(progress, 95),
                    f"Epoch {self.current_epoch + 1}/{self.total_epochs} - Batch {batch + 1}/{self.total_batches} - Acc: {acc:.4f}"
                )
                
            def on_epoch_end(self, epoch, logs=None):
                if self.outer_callback:
                    progress = int(((epoch + 1) / self.total_epochs) * 100)
                    metrics = logs or {}
                    acc = _coerce_scalar_metric(metrics.get('accuracy', 0))
                    val_acc = _coerce_scalar_metric(metrics.get('val_accuracy', 0))
                    self.outer_callback(progress, f"Epoch {epoch+1}/{self.total_epochs} - Acc: {acc:.4f} - Val Acc: {val_acc:.4f}")

        if callback:
            callback(5, "正在初始化深度学习环境...")

        self.set_config({
            'epochs': epochs,
            'batch_size': batch_size,
            'learning_rate': learning_rate,
        })

        # 特征提取
        if callback:
            callback(10, "正在提取文本特征...")
        self._create_vectorizer()
        features = self.vectorizer.fit_transform(texts).toarray()
        encoded_labels = self._encode_labels(labels)
        
        # 填充序列
        if callback:
            callback(15, "正在处理序列数据...")
        features_padded = self._pad_sequences(features)
        
        # 创建模型
        self._create_model()

        if callback:
            callback(18, f"开始训练，epochs={epochs}, batch_size={batch_size}, learning_rate={learning_rate:g}")
        
        # 训练
        callbacks_list = []
        if callback:
            callbacks_list.append(ProgressCallback(callback, epochs))
            
        history = self.keras_model.fit(
            features_padded, encoded_labels,
            epochs=epochs,
            batch_size=batch_size,
            validation_split=0.2,
            verbose=1,
            callbacks=callbacks_list
        )
        
        self.is_trained = True
        
        if callback:
            callback(100, "深度学习模型训练完成")
        
        return {
            'success': True,
            'train_accuracy': _coerce_scalar_metric(history.history.get('accuracy', [0.0])),
            'val_accuracy': _coerce_scalar_metric(history.history.get('val_accuracy', [0.0])),
            'epochs': int(epochs),
            'batch_size': int(batch_size),
            'learning_rate': float(learning_rate),
        }
    
    def _pad_sequences(self, features: np.ndarray) -> np.ndarray:
        """填充序列"""
        if features.shape[1] > self.max_sequence_length:
            return features[:, :self.max_sequence_length]
        else:
            padded = np.zeros((features.shape[0], self.max_sequence_length))
            padded[:, :features.shape[1]] = features
            return padded
    
    def predict(self, texts: List[str]) -> List[Dict]:
        """预测"""
        self.ensure_ready('预测')
        
        import tensorflow as tf
        
        features = self.vectorizer.transform(texts).toarray()
        features_padded = self._pad_sequences(features)
        
        predictions = self.keras_model.predict(features_padded)
        predicted_indices = predictions.argmax(axis=1)
        confidences = predictions.max(axis=1)
        
        categories = self.label_encoder.inverse_transform(predicted_indices)
        
        results = []
        for text, category, confidence in zip(texts, categories, confidences):
            results.append({
                'text': text[:100] + '...' if len(text) > 100 else text,
                'category': category,
                'confidence': round(float(confidence), 4)
            })
        
        return results

    def evaluate(self, texts: List[str], labels: List[str]) -> Dict:
        """评估深度学习模型性能。"""
        self.ensure_ready('评估')

        features = self.vectorizer.transform(texts).toarray()
        features_padded = self._pad_sequences(features)
        encoded_labels = self.label_encoder.transform(labels)

        predictions = self.keras_model.predict(features_padded, verbose=0).argmax(axis=1)
        results = self._build_metric_results(encoded_labels, predictions, len(texts))
        logger.info(f"深度学习模型评估完成，准确率: {results['accuracy']:.4f}")
        return results

    def get_confusion_matrix_data(self, texts: List[str], labels: List[str]) -> Dict:
        """获取深度学习模型混淆矩阵数据。"""
        self.ensure_ready('生成混淆矩阵')

        features = self.vectorizer.transform(texts).toarray()
        features_padded = self._pad_sequences(features)
        encoded_labels = self.label_encoder.transform(labels)
        predictions = self.keras_model.predict(features_padded, verbose=0).argmax(axis=1)
        return self._build_confusion_matrix_payload(encoded_labels, predictions)

    def save(self, filepath: str = None):
        """保存深度学习模型与元数据。"""
        self.ensure_ready('保存')

        if filepath is None:
            filepath = f'{self.model_name}_dl'

        save_dir = filepath[:-4] if filepath.lower().endswith('.pkl') else filepath
        os.makedirs(save_dir, exist_ok=True)

        model_path = os.path.join(save_dir, 'model.keras')
        meta_path = os.path.join(save_dir, 'metadata.pkl')

        self.keras_model.save(model_path)
        with open(meta_path, 'wb') as f:
            pickle.dump({
                'vectorizer': self.vectorizer,
                'label_encoder': self.label_encoder,
                'config': self.config,
                'categories': self.categories,
                'is_trained': self.is_trained,
                'max_sequence_length': self.max_sequence_length,
                'embedding_dim': self.embedding_dim,
            }, f)

        logger.info(f"深度学习模型已保存到: {save_dir}")
        return save_dir

    def load(self, filepath: str):
        """加载深度学习模型与元数据。"""
        if not os.path.isdir(filepath):
            raise ValueError(
                f"深度学习模型存档格式无效: {filepath}。旧版 .pkl 文件不包含 Keras 权重，请重新训练并保存模型"
            )

        try:
            import tensorflow as tf
        except ImportError as exc:
            raise ValueError("TensorFlow 未安装，无法加载深度学习模型") from exc

        meta_path = os.path.join(filepath, 'metadata.pkl')
        model_path = os.path.join(filepath, 'model.keras')

        if not os.path.exists(meta_path) or not os.path.exists(model_path):
            raise ValueError(f"深度学习模型文件不完整: {filepath}")

        with open(meta_path, 'rb') as f:
            meta = pickle.load(f)

        self.vectorizer = meta['vectorizer']
        self.label_encoder = meta['label_encoder']
        self.config = meta.get('config', self.config)
        self.categories = meta.get('categories', self.categories)
        self.is_trained = meta.get('is_trained', True)
        self.max_sequence_length = meta.get('max_sequence_length', self.max_sequence_length)
        self.embedding_dim = meta.get('embedding_dim', self.embedding_dim)

        self.keras_model = tf.keras.models.load_model(model_path)
        self.model = self.keras_model

        logger.info(f"深度学习模型已从 {filepath} 加载")


class BertClassifier(TextClassifier):
    """基于 BERT 的文本分类器 (Hugging Face Transformers)"""
    
    def __init__(self, model_name: str = 'bert_classifier'):
        super().__init__(model_name)
        self.tokenizer = None
        self.bert_model = None
        self.device = None
        self.trainer = None
        self.max_length = 128
        
    def _check_imports(self):
        """检查必要依赖"""
        try:
            import torch
            import transformers
            return True
        except ImportError:
            logger.error("缺少 transformers 或 torch 库，无法使用 BERT 模型。请安装: pip install transformers torch accelerate")
            return False

    def _init_device(self):
        import torch
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        logger.info(f"使用设备: {self.device}")

    def _create_model(self):
        """创建/加载 BERT 模型"""
        if not self._check_imports():
            return
            
        from transformers import BertTokenizer, BertForSequenceClassification
        import torch
        
        self._init_device()
        
        pretrained = resolve_pretrained_model_path(self.config.get('pretrained_model', DEFAULT_BERT_MODEL_ID))
        logger.info(f"加载预训练模型: {pretrained}")
        
        try:
            self.tokenizer = BertTokenizer.from_pretrained(pretrained)
            self.bert_model = BertForSequenceClassification.from_pretrained(
                pretrained,
                num_labels=len(self.categories),
                ignore_mismatched_sizes=True
            ).to(self.device)
            self.model = self.bert_model
            logger.info("BERT 模型加载成功")
        except Exception as e:
            logger.error(f"BERT 模型加载失败: {e}")
            raise

    def is_ready(self) -> bool:
        """检查 BERT 模型是否具备推理/评估所需的核心组件。"""
        return bool(
            self.is_trained and
            self.bert_model is not None and
            self.tokenizer is not None and
            self.label_encoder is not None
        )

    def _extract_model_outputs(self, outputs):
        """兼容 Hugging Face 与自定义模型输出。"""
        loss = getattr(outputs, 'loss', None)
        logits = getattr(outputs, 'logits', None)

        if logits is None and isinstance(outputs, dict):
            loss = outputs.get('loss')
            logits = outputs.get('logits')

        if logits is None and isinstance(outputs, tuple):
            if len(outputs) >= 2:
                loss, logits = outputs[:2]
            elif len(outputs) == 1:
                logits = outputs[0]

        return loss, logits

    def _create_dataset(self, encodings, encoded_labels=None):
        """创建统一的数据集对象。"""
        import torch
        from torch.utils.data import Dataset

        class NewsDataset(Dataset):
            def __init__(self, inputs, labels=None):
                self.inputs = inputs
                self.labels = labels

            def __getitem__(self, idx):
                item = {key: torch.tensor(val[idx]) for key, val in self.inputs.items()}
                if self.labels is not None:
                    item['labels'] = torch.tensor(self.labels[idx])
                return item

            def __len__(self):
                return len(next(iter(self.inputs.values())))

        return NewsDataset(encodings, encoded_labels)

    def _encode_texts(self, texts: List[str]):
        """统一的 BERT 文本编码入口。"""
        return self.tokenizer(
            texts,
            truncation=True,
            padding=True,
            max_length=self.max_length
        )

    def _predict_encoded_labels(self, texts: List[str], batch_size: int = 16):
        """返回编码后的预测标签，供评估和混淆矩阵复用。"""
        import torch
        from torch.utils.data import DataLoader

        encodings = self._encode_texts(texts)
        dataset = self._create_dataset(encodings)
        data_loader = DataLoader(dataset, batch_size=batch_size)

        self.bert_model.eval()
        predictions = []

        with torch.no_grad():
            for batch in data_loader:
                input_ids = batch['input_ids'].to(self.device)
                attention_mask = batch['attention_mask'].to(self.device)

                outputs = self.bert_model(input_ids, attention_mask=attention_mask)
                _, logits = self._extract_model_outputs(outputs)
                predicted = torch.argmax(logits, dim=1)
                predictions.extend(predicted.cpu().numpy().tolist())

        return np.asarray(predictions)

    def train(self, texts: List[str], labels: List[str], 
             epochs: int = 3, batch_size: int = 16, learning_rate: float = 2e-5,
             use_fgm: bool = False, fgm_epsilon: float = 1.0, callback=None) -> Dict:
        """训练 BERT 模型

        Args:
            use_fgm: 是否启用 FGM 对抗训练（在 embedding 空间施加扰动增强泛化）
            fgm_epsilon: FGM 扰动大小，默认 1.0
        """
        if not self._check_imports():
            return {'success': False, 'error': 'Missing dependencies'}
            
        import torch
        from torch.utils.data import Dataset, DataLoader
        
        # 兼容性处理：优先从 torch.optim 导入 AdamW，避免 transformers 旧版本或冲突问题
        try:
            from torch.optim import AdamW
        except ImportError:
            try:
                from transformers import AdamW
            except ImportError:
                # 如果都失败，记录错误但继续尝试（可能会在运行时崩溃）
                logger.error("无法导入 AdamW 优化器，请检查 torch 或 transformers 版本")
                raise
                
        from transformers import get_linear_schedule_with_warmup
        
        if callback:
            callback(5, "正在初始化 BERT 模型...")
        
        # 1. 准备数据
        self._create_model()
        encoded_labels = self._encode_labels(labels)

        # 计算类别权重（逆频率加权），缓解类别不均衡对 F1 的影响
        label_counts = Counter(encoded_labels)
        num_classes = len(label_counts)
        total_samples = len(encoded_labels)
        class_weights = torch.tensor(
            [total_samples / (num_classes * label_counts.get(i, 1)) for i in range(num_classes)],
            dtype=torch.float
        ).to(self.device) if num_classes > 0 else None
        logger.info(f"类别加权损失已启用，{num_classes} 个类别，权重范围: "
                     f"{class_weights.min().item():.2f} ~ {class_weights.max().item():.2f}" if class_weights is not None else "未启用")

        # 检测模型是否支持 class_weights 参数（自定义 BertTextCNNModel 支持，HuggingFace 原生模型不支持）
        import inspect
        _model_supports_weights = 'class_weights' in inspect.signature(self.bert_model.forward).parameters
        
        # Tokenize
        if callback:
            callback(10, "正在进行文本 Tokenization...")
        encodings = self._encode_texts(texts)
        dataset = self._create_dataset(encodings, encoded_labels)
        
        # 划分训练/验证集 (简单划分)
        train_size = int(0.8 * len(dataset))
        val_size = len(dataset) - train_size
        train_dataset, val_dataset = torch.utils.data.random_split(dataset, [train_size, val_size])
        
        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
        val_loader = DataLoader(val_dataset, batch_size=batch_size)
        
        # 2. 优化器与调度器
        optimizer = AdamW(self.bert_model.parameters(), lr=learning_rate)
        total_steps = len(train_loader) * epochs
        scheduler = get_linear_schedule_with_warmup(
            optimizer, num_warmup_steps=0, num_training_steps=total_steps
        )

        # 3. FGM 对抗训练初始化
        fgm = None
        if use_fgm:
            fgm = FGM(self.bert_model, epsilon=fgm_epsilon)
            logger.info(f"FGM 对抗训练已启用，epsilon={fgm_epsilon}")
        
        # 4. 训练循环
        fgm_label = "+FGM" if use_fgm else ""
        logger.info(
            f"开始 BERT{fgm_label} 微调，Epochs: {epochs}, Batch Size: {batch_size}, Learning Rate: {learning_rate:g}"
        )
        if callback:
            callback(
                15,
                f"开始训练{fgm_label}，epochs={epochs}, batch_size={batch_size}, learning_rate={learning_rate:g}"
            )
        
        history = {'train_loss': [], 'val_acc': []}
        
        for epoch in range(epochs):
            # 训练阶段
            self.bert_model.train()
            total_loss = 0
            
            # 批次进度
            num_batches = len(train_loader)
            
            for i, batch in enumerate(train_loader):
                optimizer.zero_grad()
                
                input_ids = batch['input_ids'].to(self.device)
                attention_mask = batch['attention_mask'].to(self.device)
                labels = batch['labels'].to(self.device)
                
                forward_kwargs = dict(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
                if _model_supports_weights:
                    forward_kwargs['class_weights'] = class_weights

                outputs = self.bert_model(**forward_kwargs)

                loss, _ = self._extract_model_outputs(outputs)
                total_loss += loss.item()
                
                loss.backward()

                # FGM 对抗训练步骤：对 embedding 加扰动后二次前向+反向
                if fgm is not None:
                    fgm.attack()
                    outputs_adv = self.bert_model(**forward_kwargs)
                    loss_adv, _ = self._extract_model_outputs(outputs_adv)
                    loss_adv.backward()
                    fgm.restore()

                torch.nn.utils.clip_grad_norm_(self.bert_model.parameters(), 1.0)
                optimizer.step()
                scheduler.step()
                
                # 细粒度进度更新 (每个 epoch 占用 80% / epochs 的进度条)
                if callback and i % 10 == 0:
                    epoch_progress = (i / num_batches) * (80 / epochs)
                    base_progress = 15 + (epoch * (80 / epochs))
                    current_progress = int(base_progress + epoch_progress)
                    callback(current_progress, f"Epoch {epoch+1}/{epochs} - Batch {i}/{num_batches}")
            
            avg_train_loss = total_loss / len(train_loader)
            history['train_loss'].append(avg_train_loss)
            
            # 验证阶段
            if callback:
                callback(int(15 + ((epoch + 1) * (80 / epochs))), f"Epoch {epoch+1} - 正在验证...")
                
            self.bert_model.eval()
            correct = 0
            total = 0
            
            with torch.no_grad():
                for batch in val_loader:
                    input_ids = batch['input_ids'].to(self.device)
                    attention_mask = batch['attention_mask'].to(self.device)
                    labels = batch['labels'].to(self.device)
                    
                    outputs = self.bert_model(
                        input_ids, 
                        attention_mask=attention_mask
                    )

                    _, logits = self._extract_model_outputs(outputs)
                    predictions = torch.argmax(logits, dim=1)
                    correct += (predictions == labels).sum().item()
                    total += labels.size(0)
            
            val_acc = correct / total
            history['val_acc'].append(val_acc)
            
            msg = f"Epoch {epoch+1}/{epochs} | Loss: {avg_train_loss:.4f} | Val Acc: {val_acc:.4f}"
            logger.info(msg)
            if callback:
                callback(int(15 + ((epoch + 1) * (80 / epochs))), msg)
            
        self.is_trained = True
        if callback:
            callback(100, "BERT 模型训练完成")
            
        return {
            'success': True,
            'history': history,
            'final_val_acc': history['val_acc'][-1]
        }

    def predict(self, texts: List[str]) -> List[Dict]:
        """BERT 预测"""
        self.ensure_ready('预测')
        if not self._check_imports():
            return []
            
        import torch
        
        self.bert_model.eval()
        results = []
        
        # 批量处理以避免显存溢出 (这里简单起见逐条或小批量)
        batch_size = 8
        
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i+batch_size]
            
            inputs = self.tokenizer(
                batch_texts,
                return_tensors="pt",
                truncation=True,
                padding=True,
                max_length=self.max_length
            ).to(self.device)
            
            with torch.no_grad():
                outputs = self.bert_model(**inputs)
                _, logits = self._extract_model_outputs(outputs)
                probs = torch.nn.functional.softmax(logits, dim=1)
                
            confidences, indices = torch.max(probs, dim=1)
            
            predicted_categories = self.label_encoder.inverse_transform(indices.cpu().numpy())
            confidences = confidences.cpu().numpy()
            
            for text, cat, conf in zip(batch_texts, predicted_categories, confidences):
                results.append({
                    'text': text[:100] + '...' if len(text) > 100 else text,
                    'category': cat,
                    'confidence': round(float(conf), 4)
                })
                
        return results

    def evaluate(self, texts: List[str], labels: List[str]) -> Dict:
        """评估 BERT 模型性能。"""
        self.ensure_ready('评估')

        encoded_labels = self.label_encoder.transform(labels)
        predictions = self._predict_encoded_labels(texts)
        results = self._build_metric_results(encoded_labels, predictions, len(texts))
        logger.info(f"BERT 模型评估完成，准确率: {results['accuracy']:.4f}")
        return results

    def get_confusion_matrix_data(self, texts: List[str], labels: List[str]) -> Dict:
        """获取 BERT 模型混淆矩阵。"""
        self.ensure_ready('生成混淆矩阵')

        encoded_labels = self.label_encoder.transform(labels)
        predictions = self._predict_encoded_labels(texts)
        return self._build_confusion_matrix_payload(encoded_labels, predictions)
        
    def save(self, filepath: str = None):
        """保存 BERT 模型 (保存为 HuggingFace 格式)"""
        if filepath is None:
            filepath = f'{self.model_name}_bert'
            
        if not os.path.exists(filepath):
            os.makedirs(filepath)
            
        # 保存模型和分词器
        self.bert_model.save_pretrained(filepath)
        self.tokenizer.save_pretrained(filepath)
        
        # 保存元数据 (LabelEncoder 等)
        meta_path = os.path.join(filepath, 'metadata.pkl')
        with open(meta_path, 'wb') as f:
            pickle.dump({
                'label_encoder': self.label_encoder,
                'categories': self.categories,
                'config': self.config,
                'is_trained': self.is_trained
            }, f)
            
        logger.info(f"BERT 模型已保存至: {filepath}")
        return filepath

    def load(self, filepath: str):
        """加载 BERT 模型"""
        if not self._check_imports():
            return
            
        from transformers import BertTokenizer, BertForSequenceClassification
        import torch
        
        self._init_device()
        
        # 加载元数据
        meta_path = os.path.join(filepath, 'metadata.pkl')
        with open(meta_path, 'rb') as f:
            meta = pickle.load(f)
            self.label_encoder = meta['label_encoder']
            self.categories = meta['categories']
            self.config = meta.get('config', {})
            self.is_trained = meta.get('is_trained', True)
            
        # 加载模型
        self.tokenizer = BertTokenizer.from_pretrained(filepath)
        self.bert_model = BertForSequenceClassification.from_pretrained(filepath).to(self.device)
        self.model = self.bert_model
        
        logger.info(f"BERT 模型已从 {filepath} 加载")


class BertTextCNNClassifier(BertClassifier):
    """BERT+TextCNN 混合模型 (基于 BERT 的增强实现)"""
    
    def __init__(self, model_name: str = 'bert_textcnn_classifier'):
        super().__init__(model_name)
        # 扩展配置以支持 TextCNN 特性
        self.config.update({
            'use_textcnn': True,
            'kernel_sizes': [3, 4, 5],
            'num_filters': 100,
            'dropout': 0.3,
            'description': 'BERT+TextCNN+规则后处理混合架构'
        })

    def _create_model(self):
        """创建真正的 BERT+TextCNN 融合模型。"""
        if not self._check_imports():
            return

        import torch
        import torch.nn as nn
        from transformers import BertModel, BertTokenizer

        self._init_device()
        pretrained = resolve_pretrained_model_path(self.config.get('pretrained_model', DEFAULT_BERT_MODEL_ID))
        kernel_sizes = [int(size) for size in self.config.get('kernel_sizes', [3, 4, 5])]
        num_filters = int(self.config.get('num_filters', 100))
        dropout_rate = float(self.config.get('dropout', 0.3))
        num_labels = len(self.categories)

        logger.info(f"加载 BERT+TextCNN 预训练模型: {pretrained}")
        self.tokenizer = BertTokenizer.from_pretrained(pretrained)

        class BertTextCNNModel(nn.Module):
            def __init__(self, model_name: str, label_count: int, conv_kernel_sizes: List[int], filters: int, dropout: float):
                super().__init__()
                self.bert = BertModel.from_pretrained(model_name)
                hidden_size = self.bert.config.hidden_size
                self.convs = nn.ModuleList([
                    nn.Conv1d(hidden_size, filters, kernel_size=size)
                    for size in conv_kernel_sizes
                ])
                self.dropout = nn.Dropout(dropout)
                self.classifier = nn.Linear(hidden_size + filters * len(conv_kernel_sizes), label_count)

            def forward(self, input_ids, attention_mask=None, labels=None, class_weights=None):
                outputs = self.bert(input_ids=input_ids, attention_mask=attention_mask)
                sequence_output = outputs.last_hidden_state
                pooled_output = outputs.pooler_output

                conv_input = sequence_output.transpose(1, 2)
                conv_features = []
                for conv in self.convs:
                    activated = torch.relu(conv(conv_input))
                    pooled = torch.max(activated, dim=2).values
                    conv_features.append(pooled)

                textcnn_features = torch.cat(conv_features, dim=1)
                combined_features = torch.cat([pooled_output, textcnn_features], dim=1)
                logits = self.classifier(self.dropout(combined_features))

                loss = None
                if labels is not None:
                    loss_fn = nn.CrossEntropyLoss(weight=class_weights)
                    loss = loss_fn(logits, labels)

                return SimpleNamespace(loss=loss, logits=logits)

        self.bert_model = BertTextCNNModel(
            pretrained,
            num_labels,
            kernel_sizes,
            num_filters,
            dropout_rate
        ).to(self.device)
        self.model = self.bert_model
        logger.info("BERT+TextCNN 模型加载成功")

    def save(self, filepath: str = None):
        """保存 BERT+TextCNN 模型。"""
        if filepath is None:
            filepath = f'{self.model_name}_bert_textcnn'

        if not os.path.exists(filepath):
            os.makedirs(filepath)

        import torch

        self.tokenizer.save_pretrained(filepath)
        torch.save(self.bert_model.state_dict(), os.path.join(filepath, 'model_state.bin'))

        meta_path = os.path.join(filepath, 'metadata.pkl')
        with open(meta_path, 'wb') as f:
            pickle.dump({
                'label_encoder': self.label_encoder,
                'categories': self.categories,
                'config': self.config,
                'is_trained': self.is_trained,
                'max_length': self.max_length
            }, f)

        logger.info(f"BERT+TextCNN 模型已保存至: {filepath}")
        return filepath

    def load(self, filepath: str):
        """加载 BERT+TextCNN 模型。"""
        import torch

        self._init_device()

        meta_path = os.path.join(filepath, 'metadata.pkl')
        with open(meta_path, 'rb') as f:
            meta = pickle.load(f)
            self.label_encoder = meta['label_encoder']
            self.categories = meta['categories']
            self.config = meta.get('config', self.config)
            self.is_trained = meta.get('is_trained', True)
            self.max_length = meta.get('max_length', self.max_length)

        self._create_model()
        model_path = os.path.join(filepath, 'model_state.bin')
        state_dict = torch.load(model_path, map_location=self.device)
        self.bert_model.load_state_dict(state_dict)
        self.bert_model.to(self.device)
        self.model = self.bert_model

        logger.info(f"BERT+TextCNN 模型已从 {filepath} 加载")


class ModelTrainer:
    """模型训练管理器"""
    
    def __init__(self):
        self.classifiers = {}
        self.current_model = None
        self.training_history = []
    
    def create_classifier(self, name: str, model_type: str = 'svm') -> TextClassifier:
        """创建分类器"""
        if model_type == 'bert':
            classifier = BertClassifier(model_name=name)
        elif model_type == 'bert_textcnn':
            classifier = BertTextCNNClassifier(model_name=name)
        elif model_type in ['cnn', 'lstm']:
            classifier = DeepLearningClassifier(model_name=name)
        else:
            classifier = TextClassifier(model_name=name)
            
        classifier.set_config({'model_type': model_type})
        self.classifiers[name] = classifier
        return classifier
    
    def train_model(self, name: str, texts: List[str], labels: List[str]) -> Dict:
        """训练指定模型"""
        if name not in self.classifiers:
            self.create_classifier(name)
        
        classifier = self.classifiers[name]
        result = classifier.train(texts, labels)
        
        if result['success']:
            self.current_model = classifier
            self.training_history.append({
                'name': name,
                'timestamp': datetime.now().isoformat(),
                **result
            })
        
        return result
    
    def compare_models(self, texts: List[str], labels: List[str]) -> Dict:
        """比较多个模型"""
        results = {}
        
        for name, classifier in self.classifiers.items():
            try:
                eval_result = classifier.evaluate(texts, labels)
                results[name] = eval_result
            except Exception as e:
                logger.error(f"评估模型 {name} 失败: {e}")
        
        return results
    
    def get_best_model(self, texts: List[str], labels: List[str]) -> Tuple[TextClassifier, Dict]:
        """获取最佳模型"""
        comparison = self.compare_models(texts, labels)
        
        if not comparison:
            return None, {}
        
        best_name = max(comparison.keys(), key=lambda x: comparison[x].get('accuracy', 0))
        return self.classifiers[best_name], comparison[best_name]


def train_news_classifier(train_file: str, model_output: str = None,
                         model_type: str = 'svm') -> Dict:
    """
    训练新闻分类器
    
    Args:
        train_file: 训练数据文件路径 (CSV/JSON)
        model_output: 模型输出路径
        model_type: 模型类型
        
    Returns:
        训练结果
    """
    # 加载数据
    if train_file.endswith('.csv'):
        df = pd.read_csv(train_file, encoding='utf-8')
    elif train_file.endswith('.json'):
        df = pd.read_json(train_file, orient='records')
    else:
        raise ValueError(f"不支持的文件格式: {train_file}")
    
    # 准备数据
    texts = []
    labels = []
    
    for _, row in df.iterrows():
        title = str(row.get('title', ''))
        content = str(row.get('content', ''))
        category = str(row.get('category', '未分类'))
        
        combined = f"{title} {content}".strip()
        if combined:
            texts.append(combined)
            labels.append(category)
    
    # 训练模型
    classifier = TextClassifier()
    result = classifier.train(texts, labels)
    
    # 评估模型
    if result['success']:
        eval_result = classifier.evaluate(texts, labels)
        result['evaluation'] = eval_result
    
    # 保存模型
    if model_output is None:
        model_output = f'news_classifier_{model_type}.pkl'
    
    if result['success']:
        classifier.save(model_output)
    
    return result


if __name__ == '__main__':
    # 简单测试
    print("=" * 50)
    print("短文本新闻分类模型测试")
    print("=" * 50)
    
    # 准备测试数据
    train_data = [
        ("国务院新闻办举行新闻发布会，介绍相关政策情况", "政治"),
        ("央行下调存款准备金率，释放流动性支持实体经济", "经济"),
        ("NBA季后赛激烈进行，湖人战胜勇士晋级决赛", "体育"),
        ("某明星演唱会门票开售，瞬间被抢购一空", "娱乐"),
        ("华为发布新一代旗舰手机，搭载最新芯片技术", "科技"),
        ("教育部发布新政策，规范校外培训机构管理", "教育"),
    ]
    
    texts = [item[0] for item in train_data]
    labels = [item[1] for item in train_data]
    
    # 训练模型
    classifier = TextClassifier(model_name='test_classifier')
    result = classifier.train(texts, labels)
    
    print(f"\n训练结果: {result}")
    
    # 测试预测
    test_texts = [
        "国家主席发表重要讲话，强调深化改革开放",
        "股市大涨，上证指数突破3000点",
        "世界杯决赛阿根廷夺冠，梅西捧杯",
    ]
    
    print("\n预测结果:")
    for text in test_texts:
        pred = classifier.predict_single(text)
        print(f"  文本: {text[:30]}...")
        print(f"  预测: {pred['category']}, 置信度: {pred['confidence']}")
        print()

