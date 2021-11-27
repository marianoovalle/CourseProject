from collections import defaultdict
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils import data
import random
import string
import os

ALL_PUNCT = string.punctuation
PAD = '<PAD>'
END = '<END>'
UNK = '<UNK>'
THRESHOLD = 5
MAX_LEN = 100
BATCH_SIZE = 32
LEARNING_RATE = 5e-4
EPOCHS = 20
device = torch.device("cpu")

class TextDataset(data.Dataset):
    def __init__(self, examples, split, threshold, max_len, idx2word=None, word2idx=None):
        self.examples = examples
        assert split in {'train', 'val', 'test'}
        self.split = split
        self.threshold = threshold
        self.max_len = max_len

        # Dictionaries
        self.idx2word = idx2word
        self.word2idx = word2idx
        if split == 'train':
            self.build_dictionary()
        self.vocab_size = len(self.word2idx)
        
        # Convert text to indices
        self.textual_ids = []
        self.convert_text()

    
    def build_dictionary(self): 
        assert self.split == 'train'
        
        # Don't change this
        self.idx2word = {0:PAD, 1:END, 2: UNK}
        self.word2idx = {PAD:0, END:1, UNK: 2}

        freq = {}
        for label, doc in self.examples:
            for word in doc:
                word = word.lower()
                if word in freq:
                    freq[word] += 1
                else:
                    freq[word] = 1

        cur_idx = 3
        for word in freq:
            if freq[word] >= self.threshold:
                self.idx2word[cur_idx] = word
                self.word2idx[word] = cur_idx
                cur_idx += 1
    
    def convert_text(self):
        for label, doc in self.examples:
            converted_doc = []
            for word in doc:
                word = word.lower()
                if word in self.word2idx:
                    converted_doc.append(self.word2idx[word])
                else:
                    converted_doc.append(self.word2idx[UNK])
            converted_doc.append(self.word2idx[END])
            self.textual_ids.append(converted_doc)

    def get_text(self, idx):
        if idx > len(self.textual_ids):
            print(len(self.examples))
            print(len(self.textual_ids))
            print("INDEX OUT OF BOUNDS")
        review = self.textual_ids[idx]
        if len(review) < self.max_len:
            review.extend([self.word2idx[PAD]] * (self.max_len - len(review)))
        return torch.LongTensor(review[:self.max_len])
    
    def get_label(self, idx):
        label, doc = self.examples[idx]
        if label == 1:
            return torch.tensor(1)
        else:
            return torch.tensor(0)

    def __len__(self):
        return len(self.examples)
    
    def __getitem__(self, idx):
        return self.get_text(idx), self.get_label(idx)

class RNN(nn.Module):
    def __init__(self, vocab_size, embed_size, hidden_size, num_layers, bidirectional, dropout, num_classes, pad_idx):
        super(RNN, self).__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.bidirectional = bidirectional
        
        # Create embed layer
        self.embedding_layer = torch.nn.Embedding(vocab_size, embed_size, pad_idx)

        # Create a rbb
        self.gru_layer = torch.nn.GRU(bidirectional=bidirectional, hidden_size=hidden_size, num_layers=num_layers, dropout=dropout, batch_first=True, input_size=embed_size)
        
        # Create a dropout
        self.dropout_layer = torch.nn.Dropout(dropout)

        # Define a linear layer 
        if self.bidirectional:
            self.linear_layer = torch.nn.Linear(2*hidden_size, num_classes)
        else:
            self.linear_layer = torch.nn.Linear(hidden_size, num_classes)
        self.prev_hidden_state = None

    def forward(self, texts):

        # Pass texts through your embedding layer to convert from word ids to word embeddings
        #   Resulting: shape: [batch_size, max_len, embed_size]
        embedding_output = self.embedding_layer(texts)
        

        # Pass the result through your recurrent network
        #   See PyTorch documentation for resulting shape for nn.GRU
        hidden_state = None
        _, hidden_state = self.gru_layer(embedding_output)
        
        # Concatenate the outputs of the last timestep for each direction (see torch.cat(...))
        #   This depends on whether or not your model is bidirectional.
        #   Resulting shape: [batch_size, num_dirs*hidden_size]
        gru_output = None
        if self.bidirectional:
            gru_output = torch.cat([hidden_state[-2], hidden_state[-1]], 1)
        else:
            gru_output = hidden_state[-1]
        
        # Apply dropout
        dropout_output = self.dropout_layer(gru_output)

        # Pass your output through the linear layer and return its output 
        #   Resulting shape: [batch_size, num_classes]
        final_output = self.linear_layer(dropout_output)

        
        return final_output

def preprocess(line):
    row = list(line.split(",")[i] for i in [0, 5])
    row[0] = int(row[0][1])
    if row[0] == 2:
        return None
    if row[0] == 4:
        row[0] = 1
    # for punct in ALL_PUNCT:
    #     if punct != "@":
    #         row[1] = row[1].replace(punct, "")
    # row[1] = row[1][1:-1].split(" ")
    row[1] = preprocess_string(row[1][1:-1])
    return row

def preprocess_string(in_str):
    out_str = in_str
    for punct in ALL_PUNCT:
        if punct != "@":
            out_str = out_str.replace(punct, "")
    return out_str.split(" ")

def accuracy(output, labels):
    preds = output.argmax(dim=1)
    correct = (preds == labels).sum().float()
    acc = correct / len(labels)
    return acc

def train(model, epochs, loader, optimizer, criterion):
    model.train()
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    for cur_epoch in range(0, epochs):
        epoch_loss = 0
        epoch_acc = 0
        for texts, labels in loader:
            texts = texts.to(device)
            labels = labels.to(device)
            optimizer.zero_grad()
            output = model(texts)
            acc = accuracy(output, labels)
            loss = criterion(output, labels)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()
            epoch_acc += acc.item()
        print("Epoch " + str(cur_epoch + 1) + " Loss: " + str(epoch_loss / len(loader)))
        print("Epoch " + str(cur_epoch + 1) + " Acc: " + str(100 * epoch_acc / len(loader)))
    print("Done Training")

def evaluate(model, loader, criterion):
    model.eval()
    epoch_loss = 0
    epoch_acc = 0
    all_predictions = []
    for texts, labels in loader:
        texts = texts.to(device)
        labels = labels.to(device)
        output = model(texts)
        acc = accuracy(output, labels)
        pred = output.argmax(dim=1)
        all_predictions.append(pred)

        loss = criterion(output, labels)

        epoch_loss += loss.item()
        epoch_acc += acc.item()
    
    acc = 100*epoch_acc/len(loader)
    loss = epoch_loss/len(loader)
    print("Test Loss: " + str(loss))
    print("Test Acc: " + str(acc))
    predictions = torch.cat(all_predictions)
    return predictions, acc, loss

def predict(model, idx2word, word2idx, tweets):
    data = [[0, preprocess_string(x)] for x in tweets]

    dataset = TextDataset(data, "test", THRESHOLD, MAX_LEN, idx2word, word2idx)
    loader = torch.utils.data.DataLoader(dataset, batch_size=1, shuffle=False, num_workers=1, drop_last=False)
    # dataset = TextDataset(data, "test", THRESHOLD, MAX_LEN)
    # loader = torch.utils.data.DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True, num_workers=2, drop_last=True)
    model.eval()
    all_predictions = []
    for tweet_batch, _ in loader:
        tweet_batch = tweet_batch.to(device)
        out = model(tweet_batch)
        all_predictions.append(out.argmax(dim=1))
    predictions = torch.cat(all_predictions)
    return predictions.tolist()

def build_model(force_rebuild=False):

    # Load training data
    print("Loading Training Data")
    training_data = []
    with open("../Data/training_data.csv", "r") as f:
        i = -1
        for line in f:
            i += 1
            if i % 40 != 0:    # Only load 1/160 of the training data
                continue
            
            row = preprocess(line)
            if row is not None:
                training_data.append(row)
    training_dataset = TextDataset(training_data, "train", THRESHOLD, MAX_LEN)
    training_loader = torch.utils.data.DataLoader(training_dataset, batch_size=BATCH_SIZE, shuffle=True, num_workers=2, drop_last=True)
    
    # Load test data
    print("Loading Test Data")
    test_data = []
    with open("../Data/test_data.csv", "r") as f:
        for line in f:
            row = preprocess(line)
            if row is not None:
                test_data.append(row)
    test_dataset = TextDataset(test_data, "test", THRESHOLD, MAX_LEN, training_dataset.idx2word, training_dataset.word2idx)
    test_loader = torch.utils.data.DataLoader(test_dataset, batch_size=1, shuffle=False, num_workers=1, drop_last=False)

    # Check if we need to build a new model or load one
    if not force_rebuild and os.path.exists("../Data/model"):
        model = torch.load("../Data/model")
        return (model, training_dataset.idx2word, training_dataset.word2idx)

    # Build RNN
    print("Building RNN")
    model =   RNN(vocab_size=training_dataset.vocab_size,
            embed_size=128,
            hidden_size=128,
            num_layers=2,
            bidirectional=True,
            dropout=0.5,
            num_classes=2,
            pad_idx=training_dataset.word2idx[PAD])
    
    model = model.to(device)

    # Train the rnn
    print("Training RNN")
    criterion = nn.CrossEntropyLoss().to(device)
    optimizer = optim.Adam(model.parameters(), lr=LEARNING_RATE)
    train(model, EPOCHS, training_loader, optimizer, criterion)
    # evaluate(model, test_loader, criterion)
    torch.save(model, "../Data/model")
    return (model, training_dataset.idx2word, training_dataset.word2idx)