# Copyright 2018 Stanford University
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""This file contains the entrypoint to the rest of the code"""

from __future__ import absolute_import
from __future__ import division

import os
import io
import json
import sys
import logging
import time
import tensorflow as tf
from pathlib import Path


from qa_model_base import QAModel
from qa_model_base import PreQAModel
from vocab import get_glove
from official_eval_helper import get_json_data, generate_answers


logging.basicConfig(level=logging.INFO)

MAIN_DIR = os.path.relpath(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) # relative path of the main directory
DEFAULT_DATA_DIR = os.path.join(MAIN_DIR, "data") # relative path of data dir
EXPERIMENTS_DIR = os.path.join(MAIN_DIR, "experiments") # relative path of experiments dir


# High-level options
tf.compat.v1.app.flags.DEFINE_integer("gpu", 0, "Which GPU to use, if you have multiple.")
tf.compat.v1.app.flags.DEFINE_string("mode", "official_eval", "Available modes: train / show_examples / official_eval")
tf.compat.v1.app.flags.DEFINE_string("experiment_name", "", "Unique name for your experiment. This will create a directory by this name in the experiments/ directory, which will hold all data related to this experiment")
tf.compat.v1.app.flags.DEFINE_integer("num_epochs", 0, "Number of epochs to train. 0 means train indefinitely")

# Hyperparameters
tf.compat.v1.app.flags.DEFINE_float("learning_rate", 0.005, "Learning rate.")
tf.compat.v1.app.flags.DEFINE_float("max_gradient_norm", 5.0, "Clip gradients to this norm.")
tf.compat.v1.app.flags.DEFINE_float("dropout", 0.15, "Fraction of units randomly dropped on non-recurrent connections.")
tf.compat.v1.app.flags.DEFINE_integer("batch_size", 32, "Batch size to use")
tf.compat.v1.app.flags.DEFINE_integer("hidden_size", 100, "Size of the hidden states")
tf.compat.v1.app.flags.DEFINE_integer("context_len", 600, "The maximum context length of your model")
tf.compat.v1.app.flags.DEFINE_integer("question_len", 30, "The maximum question length of your model")
tf.compat.v1.app.flags.DEFINE_integer("embedding_size", 50, "Size of the pretrained word vectors. This needs to be one of the available GloVe dimensions: 50/100/200/300")

# How often to print, save, eval
tf.compat.v1.app.flags.DEFINE_integer("print_every", 5, "How many iterations to do per print.")
tf.compat.v1.app.flags.DEFINE_integer("save_every",500, "How many iterations to do per save.")
tf.compat.v1.app.flags.DEFINE_integer("eval_every", 500, "How many iterations to do per calculating loss/f1/em on dev set. Warning: this is fairly time-consuming so don't do it too often.")
tf.compat.v1.app.flags.DEFINE_integer("keep", 1, "How many checkpoints to keep. 0 indicates keep all (you shouldn't need to do keep all though - it's very storage intensive).")

# Reading and saving data
tf.compat.v1.app.flags.DEFINE_string("train_dir", "", "Training directory to save the model parameters and other info. Defaults to experiments/{experiment_name}")
tf.compat.v1.app.flags.DEFINE_string("glove_path", "", "Path to glove .txt file. Defaults to data/glove.6B.{embedding_size}d.txt")
tf.compat.v1.app.flags.DEFINE_string("data_dir", DEFAULT_DATA_DIR, "Where to find preprocessed SQuAD data for training. Defaults to data/")
tf.compat.v1.app.flags.DEFINE_string("ckpt_load_dir", "./model/", "For official_eval mode, which directory to load the "
                                                           "checkpoint fron. You need to specify this for official_eval mode.")
tf.compat.v1.app.flags.DEFINE_string("json_in_path", "", "For official_eval mode, path to JSON input file. You need to specify this for official_eval_mode.")
tf.compat.v1.app.flags.DEFINE_string("json_out_path", "predictions.json", "Output path for official_eval mode. Defaults to predictions.json")


FLAGS = tf.compat.v1.app.flags.FLAGS
#os.environ["CUDA_VISIBLE_DEVICES"] = str(FLAGS.gpu)


def initialize_model(session, model, train_dir, expect_exists):
    """
    Initializes model from train_dir.

    Inputs:
      session: TensorFlow session
      model: QAModel
      train_dir: path to directory where we'll look for checkpoint
      expect_exists: If True, throw an error if no checkpoint is found.
        If False, initialize fresh model if no checkpoint is found.
    """
    print("Looking for model at %s..." % train_dir)
    ckpt = tf.compat.v1.train.get_checkpoint_state(train_dir)

    print(ckpt)
    #time.sleep(100)

    v2_path = ckpt.model_checkpoint_path + ".index" if ckpt else ""
    if ckpt:
        if (tf.compat.v1.gfile.Exists(ckpt.model_checkpoint_path) or tf.compat.v1.gfile.Exists(v2_path)):
            print("Reading model parameters from %s" % ckpt.model_checkpoint_path)
            model.saver.restore(session, ckpt.model_checkpoint_path)
            #model.save('my_model.h5')
    else:
        if expect_exists:
            raise Exception("There is no saved checkpoint at %s" % train_dir)
        else:
            print("There is no saved checkpoint at %s. Creating model with fresh parameters." % train_dir)
            session.run(tf.compat.v1.global_variables_initializer())
            print('Num params: %d' % sum(v.get_shape().num_elements() for v in tf.compat.v1.trainable_variables()))


def main(input_path, result_path):
    # Check for Python 2

    # Print out Tensorflow version
    print("This code was developed and tested on TensorFlow 1.4.1. Your TensorFlow version: %s" % tf.__version__)

    # Define train_dir
    if not FLAGS.experiment_name and not FLAGS.train_dir and FLAGS.mode != "official_eval":
        raise Exception("You need to specify either --experiment_name or --train_dir")
    FLAGS.train_dir = FLAGS.train_dir or os.path.join(EXPERIMENTS_DIR, FLAGS.experiment_name)

    # Initialize bestmodel directory
    bestmodel_dir = os.path.join(FLAGS.train_dir, "best_checkpoint")

    # Define path for glove vecs
    FLAGS.glove_path = FLAGS.glove_path or os.path.join(DEFAULT_DATA_DIR, "glove.6B.{}d.txt".format(FLAGS.embedding_size))

    # Load embedding matrix and vocab mappings
    emb_matrix, word2id, id2word = get_glove(FLAGS.glove_path, FLAGS.embedding_size)

    # Get filepaths to train/dev datafiles for tokenized queries, contexts and answers
    if FLAGS.mode == "train":
        train_context_path = os.path.join(FLAGS.data_dir, "train.context")
        train_qn_path = os.path.join(FLAGS.data_dir, "train.question")
        train_ans_path = os.path.join(FLAGS.data_dir, "train.span")
        dev_context_path = os.path.join(FLAGS.data_dir, "dev.context")
        dev_qn_path = os.path.join(FLAGS.data_dir, "dev.question")
        dev_ans_path = os.path.join(FLAGS.data_dir, "dev.span")

    
    # Initialize model
    qa_model = QAModel(FLAGS, id2word, word2id, emb_matrix)
    

    print("**************Sleeping**********************")
    #time.sleep(10000)


    # Some GPU settings
    config=tf.compat.v1.ConfigProto()
    config.gpu_options.allow_growth = True

    # Split by mode
    if FLAGS.mode == "train":

        # Setup train dir and logfile
        if not os.path.exists(FLAGS.train_dir):
            os.makedirs(FLAGS.train_dir)
        file_handler = logging.FileHandler(os.path.join(FLAGS.train_dir, "log.txt"))
        logging.getLogger().addHandler(file_handler)

        # Save a record of flags as a .json file in train_dir
    

        # Make bestmodel dir if necessary
        if not os.path.exists(bestmodel_dir):
            os.makedirs(bestmodel_dir)

        with tf.compat.v1.Session(config=config) as sess:

            # Load most recent model
            initialize_model(sess, qa_model, FLAGS.train_dir, expect_exists=False)

            # Train
            qa_model.train(sess, train_context_path, train_qn_path, train_ans_path, dev_qn_path, dev_context_path, dev_ans_path)

    elif FLAGS.mode == "compare":
        
        new_qn_file = "my_question"
        manual_qn_file = "manual_question"
        manual_answer_file = "manual_answer_file"
        new_qn_file, manual_qn_file, manual_answer_file = open(new_qn_file), open(manual_qn_file), open(manual_answer_file)
        new_compare_model = PreQAModel(emb_matrix,FLAGS.question_len-10,word2id)
        new_compare_model.compare_questions(new_qn_file,manual_qn_file,manual_answer_file)


    elif FLAGS.mode == "official_eval":
        for file in Path(input_path).glob('**/*.json'):
            logging.info("file: {}".format(file))
            mid = os.path.relpath(str(file), input_path)
            logging.info("mid: {}".format(mid))
            dst_json = os.path.join(result_path, os.path.dirname(mid), str(file.stem) + '.json')
            logging.info("dst_json: {}".format(dst_json))
            os.makedirs(os.path.dirname(dst_json), exist_ok=True)

            # Read the JSON data from file
            qn_uuid_data, context_token_data, qn_token_data = get_json_data(str(file))

            with tf.compat.v1.Session(config=config) as sess:
                # Load model from ckpt_load_dir
                initialize_model(sess, qa_model, FLAGS.ckpt_load_dir, expect_exists=True)
                print("initialize mode complete")

                test_start_time = time.time()
                # Get a predicted answer for each example in the data
                # Return a mapping answers_dict from uuid to answer
                answers_dict = generate_answers(sess, qa_model, word2id, qn_uuid_data, context_token_data, qn_token_data)
                print(answers_dict)
                test_time = time.time() - test_start_time
                with open(str(file), 'r') as f:
                    json_obj = json.load(f)
                for element in json_obj.get("data"):
                    for para in element.get("paragraphs"):
                        context = para.get("context")
                        for qas in para.get("qas"):
                            if qas.get("answers") is None:
                                qas["answers"] = []
                            qas["answers"].append({})
                            qas["answers"][0]["text"] = answers_dict.get(qas.get("id"))
                            qas["answers"][0]["answer_start"] = context.find(answers_dict.get(qas.get("id")))

                # Write the uuid->answer mapping a to json file in root dir
                print("Writing predictions to %s..." % FLAGS.json_out_path)
                with open(dst_json, 'w', encoding='utf-8') as f:
                    f.write(json.dumps(json_obj, ensure_ascii=False))
                    print("Wrote predictions to %s" % dst_json)
            return len(answers_dict), test_time, answers_dict
    else:
        raise Exception("Unexpected value of FLAGS.mode: %s" % FLAGS.mode)