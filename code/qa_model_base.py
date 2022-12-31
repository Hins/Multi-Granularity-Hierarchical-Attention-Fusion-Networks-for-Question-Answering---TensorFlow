

"""This file defines the top-level model"""

from __future__ import absolute_import
from __future__ import division

import time
import logging
import os
import sys
import numpy as np
import tensorflow as tf
tf.compat.v1.disable_eager_execution()
from tensorflow.python.ops import variable_scope as vs
from tensorflow.python.ops import embedding_ops

from evaluate import exact_match_score, f1_score
from data_batcher import get_batch_generator
from pretty_print import print_example
from modules import RNNEncoder, SimpleSoftmaxLayer, SimpleSoftmaxLayerNew,BasicAttn,RNNEncoderLSTM

logging.basicConfig(level=logging.INFO)

from data_batcher import sentence_to_token_ids

class PreQAModel(object):

    def __init__(self,emb_matrix,max_question_len,word2id):
        self.emb_matrix=emb_matrix
        self.max_question_len=max_question_len
        self.word2id=word2id
        self.new_qn_file_ids_tensor = tf.compat.v1.placeholder(tf.compat.v1.int32,shape=[None,self.max_question_len])
        self.manual_qn_file_ids_tensor = tf.compat.v1.placeholder(tf.compat.v1.int32,shape=[None,self.max_question_len])
        self.run_op = self.compare_questions_return()

    def compare_questions_preprocess(self,new_qn_file,manual_qn_file,manual_answer_file):

        new_qn = new_qn_file.readline()
        print(new_qn)
        #time.sleep(100)
        new_qn_file_tokens,new_qn_file_ids = sentence_to_token_ids(new_qn,self.word2id)


        new_qn_file_ids += [220] * (20 - len(new_qn_file_ids))
        manual_qn = manual_qn_file.readline()
        manual_qn_ids=[]
        while manual_qn:
            manual_qn_file_tokens,manual_qn_file_ids = sentence_to_token_ids(manual_qn,self.word2id)
            manual_qn_file_ids += [10] * (20 - len(manual_qn_file_ids))
            manual_qn_ids.append(manual_qn_file_ids)
            manual_qn=manual_qn_file.readline()
        new_qn_file_ids,manual_qn_ids = np.array(new_qn_file_ids),np.array(manual_qn_ids)
        new_qn_file_ids = np.expand_dims(new_qn_file_ids,axis=0)
        print(new_qn_file_ids.shape,manual_qn_ids.shape)
        return (new_qn_file_ids,manual_qn_ids)

    def compare_questions_return(self):

        embedding_matrix = tf.compat.v1.constant(self.emb_matrix, dtype=tf.compat.v1.float32, name="emb_matrix") # shape (400002, embedding_size)
        qn_new_emb_print = embedding_ops.embedding_lookup(embedding_matrix, self.new_qn_file_ids_tensor) # shape (batch_size, question_len, embedding_size)
        qn_man_emb_print = embedding_ops.embedding_lookup(embedding_matrix, self.manual_qn_file_ids_tensor) # shape (batch_size, question_len, embedding_size)

        qn_new_emb=tf.compat.v1.Print(qn_new_emb_print,[qn_new_emb_print])
        qn_man_emb=tf.compat.v1.Print(qn_man_emb_print,[qn_man_emb_print])
        print("**************************************")
        print(qn_new_emb.get_shape().as_list())
        print(qn_man_emb.get_shape().as_list())
        tile_tensor = tf.compat.v1.constant([8,1,1])
        qn_new_emb_tile = tf.compat.v1.tile(qn_new_emb,tile_tensor)

        dot_product_cal = tf.compat.v1.multiply(qn_man_emb,qn_new_emb_tile)
        reduce_sum = tf.compat.v1.reduce_sum(dot_product_cal,axis=2)
        reduce_sum = tf.compat.v1.reduce_sum(reduce_sum,axis=1)
        #reduce_sum_div = tf.compat.v1.reduce_sum(reduce_sum,axis=0)
        #reduce_sum_div=tf.compat.v1.expand_dims(reduce_sum_div,axis=0)
        #reduce_sum_div = tf.compat.v1.tile(reduce_sum_div,[8])
        #reduce_sum = tf.compat.v1.divide(reduce_sum,reduce_sum_div)
        #reduce_sum=tf.compat.v1.nn.softmax(reduce_sum)
        return reduce_sum

    def compare_questions(self,new_qn_file,manual_qn_file,manual_answer_file):

        new_qn_file_ids,manual_qn_ids=self.compare_questions_preprocess(new_qn_file,manual_qn_file,manual_answer_file)
        reduce_sum_output=0
        with tf.compat.v1.Session() as sess:
            input_feed={}
            input_feed[self.new_qn_file_ids_tensor]=new_qn_file_ids
            input_feed[self.manual_qn_file_ids_tensor]=manual_qn_ids
            reduce_sum_output = sess.run(self.run_op,input_feed)
        print(reduce_sum_output)

class QAModel(object):
    """Top-level Question Answering module"""

    def __init__(self, FLAGS, id2word, word2id, emb_matrix):
        """
        Initializes the QA model.

        Inputs:
          FLAGS: the flags passed in from main.py
          id2word: dictionary mapping word idx (int) to word (string)
          word2id: dictionary mapping word (string) to word idx (int)
          emb_matrix: numpy array shape (400002, embedding_size) containing pre-traing GloVe embeddings
        """
        print("Initializing the QAModel...")
        self.FLAGS = FLAGS
        self.id2word = id2word
        self.word2id = word2id

        # Add all parts of the graph
        with tf.compat.v1.variable_scope("QAModel",
                                         initializer=tf.compat.v1.variance_scaling_initializer(), reuse=tf.compat.v1.AUTO_REUSE):
            self.add_placeholders()
            self.add_embedding_layer(emb_matrix)
            self.build_graph()
            self.add_loss()

            # Define trainable parameters, gradient, gradient norm, and clip by gradient norm
            params = tf.compat.v1.trainable_variables()
            gradients = tf.compat.v1.gradients(self.loss, params)
            self.gradient_norm = tf.compat.v1.global_norm(gradients)
            clipped_gradients, _ = tf.compat.v1.clip_by_global_norm(gradients, FLAGS.max_gradient_norm)
            self.param_norm = tf.compat.v1.global_norm(params)

            # Define optimizer and updates
            # (updates is what you need to fetch in session.run to do a gradient update)
            self.global_step = tf.compat.v1.Variable(0, name="global_step", trainable=False)
            opt = tf.compat.v1.train.AdamOptimizer(learning_rate=FLAGS.learning_rate) # you can try other optimizers
            self.updates = opt.apply_gradients(zip(clipped_gradients, params), global_step=self.global_step)

            # Define savers (for checkpointing) and summaries (for tensorboard)
            self.saver = tf.compat.v1.train.Saver(tf.compat.v1.global_variables(), max_to_keep=FLAGS.keep)
            self.bestmodel_saver = tf.compat.v1.train.Saver(tf.compat.v1.global_variables(), max_to_keep=1)
            self.summaries = tf.compat.v1.summary.merge_all()

    def add_placeholders(self):
        """
        Add placeholders to the graph. Placeholders are used to feed in inputs.
        """
        # Add placeholders for inputs.
        # These are all batch-first: the None corresponds to batch_size and
        # allows you to run the same model with variable batch_size
        self.context_ids = tf.compat.v1.placeholder(tf.compat.v1.int32, shape=[None, self.FLAGS.context_len],
                                                    name="context_ids")
        self.context_mask = tf.compat.v1.placeholder(tf.compat.v1.int32, shape=[None, self.FLAGS.context_len], name="context_mask")
        self.qn_ids = tf.compat.v1.placeholder(tf.compat.v1.int32, shape=[None, self.FLAGS.question_len], name="qn_ids")
        self.qn_mask = tf.compat.v1.placeholder(tf.compat.v1.int32, shape=[None, self.FLAGS.question_len], name="qn_mask")
        self.ans_span = tf.compat.v1.placeholder(tf.compat.v1.int32, shape=[None, 2], name="ans_span")

        # Add a placeholder to feed in the keep probability (for dropout).
        # This is necessary so that we can instruct the model to use dropout when training, but not when testing
        self.keep_prob = tf.compat.v1.placeholder_with_default(1.0, shape=(), name="keep_prob")

    def add_embedding_layer(self, emb_matrix):
        """
        Adds word embedding layer to the graph.

        Inputs:
          emb_matrix: shape (400002, embedding_size).
            The GloVe vectors, plus vectors for PAD and UNK.
        """
        with vs.variable_scope("embeddings"):

            # Note: the embedding matrix is a tf.compat.v1.constant which means it's not a trainable parameter
            embedding_matrix = tf.compat.v1.constant(emb_matrix, dtype=tf.compat.v1.float32, name="emb_matrix") # shape (400002, embedding_size)

            # Get the word embeddings for the context and question,
            # using the placeholders self.context_ids and self.qn_ids
            self.context_embs = embedding_ops.embedding_lookup(embedding_matrix, self.context_ids) # shape (batch_size, context_len, embedding_size)
            print("self.context_embs shape is ")
            print(self.context_embs.get_shape().as_list())
            self.qn_embs = embedding_ops.embedding_lookup(embedding_matrix, self.qn_ids) # shape (batch_size, question_len, embedding_size)
            print("self.qn_embs shape is ")
            print(self.qn_embs.get_shape().as_list())

    def build_graph_middle(self,new_attn,attn_output,context_hiddens,question_hiddens):
        blended_reps = tf.compat.v1.concat([context_hiddens, attn_output], axis=2) # (batch_size, context_len, hidden_size*4)

        # Apply fully connected layer to each blended representation
        # Note, blended_reps_final corresponds to b' in the handout
        # Note, tf.compat.v1.contrib.layers.fully_connected applies a ReLU non-linarity here by default
        blended_reps_final = tf.compat.v1.layers.dense(blended_reps, self.FLAGS.hidden_size) # blended_reps_final is shape (batch_size, context_len, hidden_size)
        return None,None,blended_reps_final

    def build_graph(self):
        """Builds the main part of the graph for the model, starting from the input embeddings to the final distributions for the answer span.

        Defines:
          self.logits_start, self.logits_end: Both tensors shape (batch_size, context_len).
            These are the logits (i.e. values that are fed into the softmax function) for the start and end distribution.
            Important: these are -large in the pad locations. Necessary for when we feed into the cross entropy function.
          self.probdist_start, self.probdist_end: Both shape (batch_size, context_len). Each row sums to 1.
            These are the result of taking (masked) softmax of logits_start and logits_end.
        """

        # Use a RNN to get hidden states for the context and the question
        # Note: here the RNNEncoder is shared (i.e. the weights are the same)
        # between the context and the question.

        encoder = RNNEncoder(self.FLAGS.hidden_size, self.keep_prob)
        encoderQ = RNNEncoder(self.FLAGS.hidden_size, self.keep_prob)
        context_hiddens = encoder.build_graph(self.context_embs, self.context_mask,"rnnencoder1") # (batch_size,
        # context_len, hidden_size*2)
        '''
        context_hiddens = tf.compat.v1.concat([self.context_embs, self.context_embs], axis=2)
        context_hiddens = tf.compat.v1.concat([context_hiddens, context_hiddens], axis=2)
        '''
        print("context_hiddens shape is ")
        print(context_hiddens.get_shape().as_list())

        question_hiddens = encoderQ.build_graph(self.qn_embs, self.qn_mask,"rnnencoderQ") # (batch_size,
        # question_len, ,"rnnencoder1"hidden_size*2)
        '''
        question_hiddens = tf.compat.v1.concat([self.qn_embs, self.qn_embs], axis=2)
        question_hiddens = tf.compat.v1.concat([question_hiddens, question_hiddens], axis=2)
        '''
        print("question_hiddens shape is ")
        print(question_hiddens.get_shape().as_list())

        # Use context hidden states to attend to question hidden states
        attn_layer = BasicAttn(self.keep_prob, self.FLAGS.hidden_size*2, self.FLAGS.hidden_size*2)
        WLin = tf.compat.v1.get_variable("WLin", [2*self.FLAGS.hidden_size, 2*self.FLAGS.hidden_size],
                                            trainable=False, initializer=tf.keras.initializers.glorot_normal())
        _, self.attn_output,self.new_attn = attn_layer.build_graph(question_hiddens, self.qn_mask,
                                                               context_hiddens, WLin,
                                                         2*self.FLAGS.hidden_size) # attn_output is shape (batch_size, context_len, hidden_size*2)

        _,_,self.blended_reps_final=self.build_graph_middle(self.new_attn, self.attn_output, context_hiddens,
                                                            question_hiddens)

        print("blended_reps_final shape is ")
        print(self.blended_reps_final.get_shape().as_list())
        print("context_mask shape is ")
        print(self.context_mask.get_shape().as_list())

        # Use softmax layer to compute probability distribution for start location
        # Note this produces self.logits_start and self.probdist_start, both of which have shape (batch_size, context_len)
        with vs.variable_scope("StartDist"):
            softmax_layer_start = SimpleSoftmaxLayer()
            self.logits_start, self.probdist_start = softmax_layer_start.build_graph(self.blended_reps_final,
                                                                                 self.context_mask)

        # Use softmax layer to compute probability distribution for end location
        # Note this produces self.logits_end and self.probdist_end, both of which have shape (batch_size, context_len)
        with vs.variable_scope("EndDist"):
            softmax_layer_end = SimpleSoftmaxLayer()
            self.logits_end, self.probdist_end = softmax_layer_start.build_graph(self.blended_reps_final,
                                                                           self.context_mask)



        '''
        
        '''
    def add_loss(self):
        """
        Add loss computation to the graph.

        Uses:
          self.logits_start: shape (batch_size, context_len)
            IMPORTANT: Assumes that self.logits_start is masked (i.e. has -large in masked locations).
            That's because the tf.compat.v1.nn.sparse_softmax_cross_entropy_with_logits
            function applies softmax and then computes cross-entropy loss.
            So you need to apply masking to the logits (by subtracting large
            number in the padding location) BEFORE you pass to the
            sparse_softmax_cross_entropy_with_logits function.

          self.ans_span: shape (batch_size, 2)
            Contains the gold start and end locations

        Defines:
          self.loss_start, self.loss_end, self.loss: all scalar tensors
        """
        with vs.variable_scope("loss"):

            # Calculate loss for prediction of start position
            loss_start = tf.compat.v1.nn.sparse_softmax_cross_entropy_with_logits(logits=self.logits_start, labels=self.ans_span[:, 0]) # loss_start has shape (batch_size)
            self.loss_start = tf.compat.v1.reduce_mean(loss_start) # scalar. avg across batch
            tf.compat.v1.summary.scalar('loss_start', self.loss_start) # log to tensorboard

            # Calculate loss for prediction of end position
            loss_end = tf.compat.v1.nn.sparse_softmax_cross_entropy_with_logits(logits=self.logits_end, labels=self.ans_span[:, 1])
            self.loss_end = tf.compat.v1.reduce_mean(loss_end)
            tf.compat.v1.summary.scalar('loss_end', self.loss_end)

            # Add the two losses
            self.loss = self.loss_start + self.loss_end
            tf.compat.v1.summary.scalar('loss', self.loss)


    def run_train_iter(self, session, batch, summary_writer):
        """
        This performs a single training iteration (forward pass, loss computation, backprop, parameter update)

        Inputs:
          session: TensorFlow session
          batch: a Batch object
          summary_writer: for Tensorboard

        Returns:
          loss: The loss (averaged across the batch) for this batch.
          global_step: The current number of training iterations we've done
          param_norm: Global norm of the parameters
          gradient_norm: Global norm of the gradients
        """
        # Match up our input data with the placeholders
        input_feed = {}
        input_feed[self.context_ids] = batch.context_ids
        #print(batch.context_ids)
        input_feed[self.context_mask] = batch.context_mask
        #print(batch.context_mask)
        input_feed[self.qn_ids] = batch.qn_ids
        #print(batch.qn_ids)
        input_feed[self.qn_mask] = batch.qn_mask
        #print(batch.qn_mask)
        input_feed[self.ans_span] = batch.ans_span
        #print(batch.ans_span)
        input_feed[self.keep_prob] = 1.0 - self.FLAGS.dropout # apply dropout

        # output_feed contains the things we want to fetch.
        output_feed = [self.updates, self.summaries, self.loss, self.global_step, self.param_norm, self.gradient_norm]

        # Run the model
        #print(session.run(output_feed, input_feed))
        session.run(tf.compat.v1.global_variables_initializer())
        [_, summaries, loss, global_step, param_norm, gradient_norm] = session.run(output_feed, feed_dict=input_feed)

        # All summaries in the graph are added to Tensorboard
        summary_writer.add_summary(summaries, global_step)

        return loss, global_step, param_norm, gradient_norm


    def get_loss(self, session, batch):
        """
        Run forward-pass only; get loss.

        Inputs:
          session: TensorFlow session
          batch: a Batch object

        Returns:
          loss: The loss (averaged across the batch) for this batch
        """

        input_feed = {}
        input_feed[self.context_ids] = batch.context_ids
        input_feed[self.context_mask] = batch.context_mask
        input_feed[self.qn_ids] = batch.qn_ids
        input_feed[self.qn_mask] = batch.qn_mask
        input_feed[self.ans_span] = batch.ans_span
        # note you don't supply keep_prob here, so it will default to 1 i.e. no dropout

        output_feed = [self.loss]

        [loss] = session.run(output_feed, input_feed)

        return loss


    def get_prob_dists(self, session, batch):
        """
        Run forward-pass only; get probability distributions for start and end positions.

        Inputs:
          session: TensorFlow session
          batch: Batch object

        Returns:
          probdist_start and probdist_end: both shape (batch_size, context_len)
        """
        input_feed = {}
        input_feed[self.context_ids] = batch.context_ids
        input_feed[self.context_mask] = batch.context_mask
        input_feed[self.qn_ids] = batch.qn_ids
        input_feed[self.qn_mask] = batch.qn_mask
        # note you don't supply keep_prob here, so it will default to 1 i.e. no dropout
        #session.run(tf.compat.v1.global_variables_initializer())
        output_feed = [self.probdist_start, self.probdist_end]
        [probdist_start, probdist_end] = session.run(output_feed, input_feed)

        return probdist_start, probdist_end


    def get_start_end_pos(self, session, batch):
        """
        Run forward-pass only; get the most likely answer span.

        Inputs:
          session: TensorFlow session
          batch: Batch object

        Returns:
          start_pos, end_pos: both numpy arrays shape (batch_size).
            The most likely start and end positions for each example in the batch.
        """
        # Get start_dist and end_dist, both shape (batch_size, context_len)
        start_dist, end_dist = self.get_prob_dists(session, batch)

        # Take argmax to get start_pos and end_post, both shape (batch_size)
        start_pos = np.argmax(start_dist, axis=1)
        end_pos = np.argmax(end_dist, axis=1)

        return start_pos, end_pos


    def get_dev_loss(self, session, dev_context_path, dev_qn_path, dev_ans_path):
        """
        Get loss for entire dev set.

        Inputs:
          session: TensorFlow session
          dev_qn_path, dev_context_path, dev_ans_path: paths to the dev.{context/question/answer} data files

        Outputs:
          dev_loss: float. Average loss across the dev set.
        """
        logging.info("Calculating dev loss...")
        tic = time.time()
        loss_per_batch, batch_lengths = [], []


        for batch in get_batch_generator(self.word2id, dev_context_path, dev_qn_path, dev_ans_path, self.FLAGS.batch_size, context_len=self.FLAGS.context_len, question_len=self.FLAGS.question_len, discard_long=True):

            # Get loss for this batch
            loss = self.get_loss(session, batch)
            curr_batch_size = batch.batch_size
            loss_per_batch.append(loss * curr_batch_size)
            batch_lengths.append(curr_batch_size)

        # Calculate average loss
        total_num_examples = sum(batch_lengths)
        toc = time.time()
        print("Computed dev loss over %i examples in %.2f seconds" % (total_num_examples, toc-tic))

        # Overall loss is total loss divided by total number of examples
        dev_loss = sum(loss_per_batch) / float(total_num_examples)

        return dev_loss


    def check_f1_em(self, session, context_path, qn_path, ans_path, dataset, num_samples=100, print_to_screen=True):
        """
        Sample from the provided (train/dev) set.
        For each sample, calculate F1 and EM score.
        Return average F1 and EM score for all samples.
        Optionally pretty-print examples.

        Note: This function is not quite the same as the F1/EM numbers you get from "official_eval" mode.
        This function uses the pre-processed version of the e.g. dev set for speed,
        whereas "official_eval" mode uses the original JSON. Therefore:
          1. official_eval takes your max F1/EM score w.r.t. the three reference answers,
            whereas this function compares to just the first answer (which is what's saved in the preprocessed data)
          2. Our preprocessed version of the dev set is missing some examples
            due to tokenization issues (see squad_preprocess.py).
            "official_eval" includes all examples.

        Inputs:
          session: TensorFlow session
          qn_path, context_path, ans_path: paths to {dev/train}.{question/context/answer} data files.
          dataset: string. Either "train" or "dev". Just for logging purposes.
          num_samples: int. How many samples to use. If num_samples=0 then do whole dataset.
          print_to_screen: if True, pretty-prints each example to screen

        Returns:
          F1 and EM: Scalars. The average across the sampled examples.
        """
        logging.info("Calculating F1/EM for %s examples in %s set..." % (str(num_samples) if num_samples != 0 else "all", dataset))

        f1_total = 0.
        em_total = 0.
        example_num = 0

        tic = time.time()


        for batch in get_batch_generator(self.word2id, context_path, qn_path, ans_path, self.FLAGS.batch_size, context_len=self.FLAGS.context_len, question_len=self.FLAGS.question_len, discard_long=False):

            pred_start_pos, pred_end_pos = self.get_start_end_pos(session, batch)

            # Convert the start and end positions to lists length batch_size
            pred_start_pos = pred_start_pos.tolist() # list length batch_size
            pred_end_pos = pred_end_pos.tolist() # list length batch_size

            for ex_idx, (pred_ans_start, pred_ans_end, true_ans_tokens) in enumerate(zip(pred_start_pos, pred_end_pos, batch.ans_tokens)):
                example_num += 1

                # Get the predicted answer
                # Important: batch.context_tokens contains the original words (no UNKs)
                # You need to use the original no-UNK version when measuring F1/EM
                pred_ans_tokens = batch.context_tokens[ex_idx][pred_ans_start : pred_ans_end + 1]
                pred_answer = " ".join(pred_ans_tokens)

                # Get true answer (no UNKs)
                true_answer = " ".join(true_ans_tokens)

                # Calc F1/EM
                f1 = f1_score(pred_answer, true_answer)
                em = exact_match_score(pred_answer, true_answer)
                f1_total += f1
                em_total += em

                # Optionally pretty-print

                if print_to_screen:
                    print_example(self.word2id, batch.context_tokens[ex_idx], batch.qn_tokens[ex_idx], batch.ans_span[ex_idx, 0], batch.ans_span[ex_idx, 1], pred_ans_start, pred_ans_end, true_answer, pred_answer, f1, em)

                if num_samples != 0 and example_num >= num_samples:
                    break

            if num_samples != 0 and example_num >= num_samples:
                break

        f1_total /= example_num
        em_total /= example_num

        toc = time.time()
        logging.info("Calculating F1/EM for %i examples in %s set took %.2f seconds" % (example_num, dataset, toc-tic))

        return f1_total, em_total


    def train(self, session, train_context_path, train_qn_path, train_ans_path, dev_qn_path, dev_context_path, dev_ans_path):
        """
        Main training loop.

        Inputs:
          session: TensorFlow session
          {train/dev}_{qn/context/ans}_path: paths to {train/dev}.{context/question/answer} data files
        """

        # Print number of model parameters
        tic = time.time()
        params = tf.compat.v1.trainable_variables()
        num_params = sum(map(lambda t: np.prod(tf.compat.v1.shape(t.value()).eval()), params))
        toc = time.time()
        logging.info("Number of params: %d (retrieval took %f secs)" % (num_params, toc - tic))

        # We will keep track of exponentially-smoothed loss
        exp_loss = None

        # Checkpoint management.
        # We keep one latest checkpoint, and one best checkpoint (early stopping)
        checkpoint_path = os.path.join(self.FLAGS.train_dir, "qa.ckpt")
        bestmodel_dir = os.path.join(self.FLAGS.train_dir, "best_checkpoint")
        bestmodel_ckpt_path = os.path.join(bestmodel_dir, "qa_best.ckpt")
        best_dev_f1 = None
        best_dev_em = None

        # for TensorBoard
        summary_writer = tf.compat.v1.summary.FileWriter(self.FLAGS.train_dir, session.graph)

        epoch = 0

        logging.info("Beginning training loop...")
        while self.FLAGS.num_epochs == 0 or epoch < self.FLAGS.num_epochs:
            epoch += 1
            epoch_tic = time.time()

            # Loop over batches
            for batch in get_batch_generator(self.word2id, train_context_path, train_qn_path, train_ans_path, self.FLAGS.batch_size, context_len=self.FLAGS.context_len, question_len=self.FLAGS.question_len, discard_long=True):

                # Run training iteration
                iter_tic = time.time()
                loss, global_step, param_norm, grad_norm = self.run_train_iter(session, batch, summary_writer)
                iter_toc = time.time()
                iter_time = iter_toc - iter_tic

                # Update exponentially-smoothed loss
                if not exp_loss: # first iter
                    exp_loss = loss
                else:
                    exp_loss = 0.99 * exp_loss + 0.01 * loss

                # Sometimes print info to screen
                if global_step % self.FLAGS.print_every == 0:
                    logging.info(
                        'epoch %d, iter %d, loss %.5f, smoothed loss %.5f, grad norm %.5f, param norm %.5f, batch time %.3f' %
                        (epoch, global_step, loss, exp_loss, grad_norm, param_norm, iter_time))

                # Sometimes save model
                if global_step % self.FLAGS.save_every == 0:
                    logging.info("Saving to %s..." % checkpoint_path)
                    self.saver.save(session, checkpoint_path, global_step=global_step)

                # Sometimes evaluate model on dev loss, train F1/EM and dev F1/EM
                if global_step % self.FLAGS.eval_every == 0:

                    # Get loss for entire dev set and log to tensorboard
                    dev_loss = self.get_dev_loss(session, dev_context_path, dev_qn_path, dev_ans_path)
                    logging.info("Epoch %d, Iter %d, dev loss: %f" % (epoch, global_step, dev_loss))
                    write_summary(dev_loss, "dev/loss", summary_writer, global_step)


                    # Get F1/EM on train set and log to tensorboard
                    train_f1, train_em = self.check_f1_em(session, train_context_path, train_qn_path, train_ans_path, "train", num_samples=1000)
                    logging.info("Epoch %d, Iter %d, Train F1 score: %f, Train EM score: %f" % (epoch, global_step, train_f1, train_em))
                    write_summary(train_f1, "train/F1", summary_writer, global_step)
                    write_summary(train_em, "train/EM", summary_writer, global_step)


                    # Get F1/EM on dev set and log to tensorboard
                    dev_f1, dev_em = self.check_f1_em(session, dev_context_path, dev_qn_path, dev_ans_path, "dev", num_samples=0)
                    logging.info("Epoch %d, Iter %d, Dev F1 score: %f, Dev EM score: %f" % (epoch, global_step, dev_f1, dev_em))
                    write_summary(dev_f1, "dev/F1", summary_writer, global_step)
                    write_summary(dev_em, "dev/EM", summary_writer, global_step)


                    # Early stopping based on dev EM. You could switch this to use F1 instead.
                    if best_dev_em is None or dev_em > best_dev_em:
                        best_dev_em = dev_em
                        logging.info("Saving to %s..." % bestmodel_ckpt_path)
                        self.bestmodel_saver.save(session, bestmodel_ckpt_path, global_step=global_step)


            epoch_toc = time.time()
            logging.info("End of epoch %i. Time for epoch: %f" % (epoch, epoch_toc-epoch_tic))

        sys.stdout.flush()



def write_summary(value, tag, summary_writer, global_step):
    """Write a single summary value to tensorboard"""
    summary = tf.compat.v1.Summary()
    summary.value.add(tag=tag, simple_value=value)
    summary_writer.add_summary(summary, global_step)
