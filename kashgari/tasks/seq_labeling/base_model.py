# encoding: utf-8
"""
@author: BrikerMan
@contact: eliyar917@gmail.com
@blog: https://eliyar.biz

@version: 1.0
@license: Apache Licence
@file: base_model
@time: 2019-01-21

"""
import random
from typing import Tuple, Dict

import numpy as np
from keras.models import Model
from keras.preprocessing import sequence
from keras.utils import to_categorical
from sklearn import metrics
from sklearn.utils import class_weight as class_weight_calculte

from kashgari import k
from kashgari.embeddings import CustomEmbedding, BaseEmbedding
from kashgari.type_hints import *


class SequenceLabelingModel(object):
    __base_hyper_parameters__ = {}

    @property
    def hyper_parameters(self):
        return self._hyper_parameters_

    def __init__(self, embedding: BaseEmbedding = None, hyper_parameters: Dict = None):
        if embedding is None:
            self.embedding = CustomEmbedding('custom', sequence_length=10, embedding_size=100)
        else:
            self.embedding = embedding
        self.model: Model = None
        self._hyper_parameters_ = self.__base_hyper_parameters__.copy()
        self._label2idx = {}
        self._idx2label = {}
        if hyper_parameters:
            self._hyper_parameters_.update(hyper_parameters)

    @property
    def label2idx(self) -> Dict[str, int]:
        return self._label2idx

    @property
    def token2idx(self) -> Dict[str, int]:
        return self.embedding.token2idx

    @label2idx.setter
    def label2idx(self, value):
        self._label2idx = value
        self._idx2label = dict([(val, key) for (key, val) in value.items()])

    def build_model(self):
        """
        build model function
        :return:
        """
        raise NotImplementedError()

    def build_token2id_label2id_dict(self,
                                     x_train: List[List[str]],
                                     y_train: List[str],
                                     x_validate: List[List[str]] = None,
                                     y_validate: List[str] = None):
        x_data = x_train
        y_data = y_train
        if x_validate:
            x_data += x_validate
            y_data += y_validate
        self.embedding.build_token2idx_dict(x_data, 3)

        label_set = set(y_data)
        label2idx = {
            k.PAD: 0,
            k.BOS: 1,
            k.EOS: 2
        }
        label_set = [i for i in label_set if i not in label2idx]
        for label in label_set:
            label2idx[label] = len(label2idx)

        self.label2idx = label2idx

    def labels_to_tokens(self,
                         label: Union[List[str], str],
                         add_eos_bos: bool = True) -> Union[List[int], int]:

        def tokenize_tokens(seq: List[str]):
            tokens = [self.label2idx[i] for i in seq]
            if add_eos_bos:
                tokens = [self.label2idx[k.BOS]] + tokens + [self.label2idx[k.EOS]]
            return tokens

        if isinstance(label[0], str):
            return tokenize_tokens(label)
        else:
            return [tokenize_tokens(l) for l in label]

    def tokens_to_labels(self,
                         token: Union[List[List[int]], List[int]],
                         tokens_length: Union[List[int], int],
                         remove_eos_bos: bool = True) -> Union[List[str], str]:
        def tokenize_tokens(seq: List[int]):
            if isinstance(token, int):
                return self._idx2label[token]
            else:
                return [self._idx2label[l] for l in token]

    def get_data_generator(self,
                           x_data: List[List[str]],
                           y_data: List[str],
                           batch_size: int = 64,
                           is_bert: bool = False):
        while True:
            page_list = list(range(len(x_data) // batch_size + 1))
            random.shuffle(page_list)
            for page in page_list:
                start_index = page * batch_size
                end_index = start_index + batch_size
                target_x = x_data[start_index: end_index]
                target_y = y_data[start_index: end_index]
                if len(target_x) == 0:
                    target_x = x_data[0: batch_size]
                    target_y = y_data[0: batch_size]

                tokenized_x = self.embedding.tokenize(target_x)
                tokenized_y = self.label_to_token(target_y)

                padded_x = sequence.pad_sequences(tokenized_x,
                                                  maxlen=self.embedding.sequence_length,
                                                  padding='post')
                padded_y = to_categorical(tokenized_y,
                                          num_classes=len(self.label2idx),
                                          dtype=np.int)
                if is_bert:
                    padded_x_seg = np.zeros(shape=(len(padded_x), self.embedding.sequence_length))
                    x_input_data = [padded_x, padded_x_seg]
                else:
                    x_input_data = padded_x
                yield (x_input_data, padded_y)

    def fit(self,
            x_train: List[List[str]],
            y_train: List[str],
            batch_size: int = 64,
            epochs: int = 5,
            x_validate: List[List[str]] = None,
            y_validate: List[str] = None,
            class_weight: bool = False,
            fit_kwargs: Dict = None,
            **kwargs):
        """

        :param x_train: list of training data.
        :param y_train: list of training target label data.
        :param batch_size: batch size for trainer model
        :param epochs: Number of epochs to train the model.
        :param x_validate: list of validation data.
        :param y_validate: list of validation target label data.
        :param y_validate: list of validation target label data.
        :param y_validate: list of validation target label data.
        :param class_weight: set class weights for imbalanced classes
        :param fit_kwargs: additional kwargs to be passed to
               :func:`~keras.models.Model.fit`
        :return:
        """
        assert len(x_train) == len(y_train)
        self.build_token2id_label2id_dict(x_train, y_train, x_validate, y_validate)

        if len(x_train) < batch_size:
            batch_size = len(x_train) // 2

        if not self.model:
            self.build_model()

        train_generator = self.get_data_generator(x_train,
                                                  y_train,
                                                  batch_size,
                                                  is_bert=self.embedding.is_bert)

        if fit_kwargs is None:
            fit_kwargs = {}

        if x_validate:
            validation_generator = self.get_data_generator(x_validate,
                                                           y_validate,
                                                           batch_size,
                                                           is_bert=self.embedding.is_bert)
            fit_kwargs['validation_data'] = validation_generator
            fit_kwargs['validation_steps'] = len(x_validate) // batch_size

        if class_weight:
            y_list = self.label_to_token(y_train)
            class_weights = class_weight_calculte.compute_class_weight('balanced',
                                                                       np.unique(y_list),
                                                                       y_list)
        else:
            class_weights = None

        self.model.fit_generator(train_generator,
                                 steps_per_epoch=len(x_train) // batch_size,
                                 epochs=epochs,
                                 class_weight=class_weights,
                                 **fit_kwargs)

    def predict(self, sentence: Union[List[str], List[List[str]]], batch_size=None):
        tokens = self.embedding.tokenize(sentence)
        is_list = not isinstance(sentence[0], str)
        if is_list:
            padded_tokens = sequence.pad_sequences(tokens,
                                                   maxlen=self.embedding.sequence_length,
                                                   padding='post')
        else:
            padded_tokens = sequence.pad_sequences([tokens],
                                                   maxlen=self.embedding.sequence_length,
                                                   padding='post')
        if self.embedding.is_bert:
            x = [padded_tokens, np.zeros(shape=(len(padded_tokens), self.embedding.sequence_length))]
        else:
            x = padded_tokens
        predict_result = self.model.predict(x, batch_size=batch_size).argmax(-1)
        labels = self.token_to_label(predict_result)
        if is_list:
            return labels
        else:
            return labels[0]

    def evaluate(self, x_data, y_data, batch_size=None) -> Tuple[float, float, Dict]:
        y_pred = self.predict(x_data, batch_size=batch_size)
        weighted_f1 = metrics.f1_score(y_data, y_pred, average='weighted')
        weighted_recall = metrics.recall_score(y_data, y_pred, average='weighted')
        report = metrics.classification_report(y_data, y_pred, output_dict=True)
        print(metrics.classification_report(y_data, y_pred))
        return weighted_f1, weighted_recall, report