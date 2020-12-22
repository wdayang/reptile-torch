# -*- coding: utf-8 -*-
"""Automated Machine Learning Torch Reptile

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1S7S0r1982CPN7O3m997byhCtO5fMAFHb

# **Automated Machine Learning**

---

### **Reptile - Scalable Metalearning**
*Fall 2020 | Research Project*

---

<font size="1">*Based on the Original Implementation by Alex Nichol & John Schulman [[1]](https://openai.com/blog/reptile/)*</font>

### Meta Libraries
"""

# System Utility
import sys

# IPython Notebook Utilities
from IPython.display import clear_output
import tqdm.notebook as tqdm
clear_output()

# Google Colab Utilities
from google.colab import files
print(sys.version)

"""### Packages"""

# Data Processing
import numpy as np
import pandas as pd

# Model Library
import tensorflow as tf

# Parallel Compute
import torch 
import torch.nn as nn

# Data Visualization
import matplotlib.pyplot as plt
from torch.utils.tensorboard import SummaryWriter

# Utility Libraries
import random
import math
from time import time
from copy import deepcopy
from datetime import datetime

# Initialize Device
device = ('cuda' if torch.cuda.is_available() else 'cpu')
print("Torch Version\t", torch.__version__)
print("Using Device\t", torch.cuda.get_device_name(0))

"""### Configuration"""

data_folder = "data"
np.random.seed(int(time()))
torch.manual_seed(int(time()))

"""### Reptile TensorFlow

#### Class Definition
"""

class Reptile:

  def __init__(self, model, log, params):

    # Intialize Reptile Parameters
    self.inner_step_size = params[0]
    self.inner_batch_size = params[1]
    self.outer_step_size = params[2]
    self.outer_iterations = params[3]
    self.meta_batch_size = params[4] 
    self.eval_iterations = params[5] 
    self.eval_batch_size = params[6]

    # Initialize Torch Model and Tensorboard
    self.model = model.to(device)
    self.log = log

  def reset(self):

    # Reset Training Gradients
    self.model.zero_grad()
    self.current_loss = 0
    self.current_batch = 0

  def train(self, task):

    # Train from Scratch
    self.reset()

    # Outer Training Loop
    for outer_iteration in tqdm.tqdm(range(self.outer_iterations)):

      # Track Current Weights
      current_weights = deepcopy(self.model.state_dict())

      # Sample a new Subtask
      samples, task_theta = sample(task)

      # Inner Training Loop
      for inner_iteration in range(self.inner_batch_size):

        # Process Meta Learning Batches
        for batch in range(0, len(sample_space), self.meta_batch_size):

          # Get Permuted Batch from Sample
          perm = np.random.permutation(len(sample_space))
          idx = perm[batch: batch + self.meta_batch_size][:, None]

          # Calculate Batch Loss
          batch_loss = self.loss(sample_space[idx], samples[idx])
          batch_loss.backward()

          # Update Model Parameters
          for theta in self.model.parameters():

            # Get Parameter Gradient
            grad = theta.grad.data

            # Update Model Parameter
            theta.data -= self.inner_step_size * grad

          # Update Model Loss from Torch Model Tensor
          loss_tensor = batch_loss.cpu()
          self.current_loss += loss_tensor.data.numpy()
          self.current_batch += 1

      # Linear Cooling Schedule
      alpha = self.outer_step_size * (1 - outer_iteration / self.outer_iterations)

      # Get Current Candidate Weights
      candidate_weights = self.model.state_dict()

      # Transfer Candidate Weights to Model State Checkpoint
      state_dict = {candidate: (current_weights[candidate] + alpha * 
                               (candidate_weights[candidate] - current_weights[candidate])) 
                                for candidate in candidate_weights}
      self.model.load_state_dict(state_dict)
      
      # Log new Training Loss
      self.log.add_scalars('Model Estimate/Loss', 
                           {'Loss' : self.current_loss / self.current_batch}, 
                           outer_iteration)

  def loss(self, x, y):

    # Reset Torch Gradient
    self.model.zero_grad()

    # Calculate Torch Tensors
    x = torch.tensor(x, device = device, dtype = torch.float32)
    y = torch.tensor(y, device = device, dtype = torch.float32)

    # Estimate over Sample
    yhat = self.model(x)

    # Regression Loss over Estimate
    loss = nn.MSELoss()
    output = loss(yhat, y)

    return output

  def predict(self, x):

    # Estimate using Torch Model
    t = torch.tensor(x, device = device, dtype = torch.float32)
    t = self.model(t)

    # Bring Torch Tensor from GPU to System Host Memory
    t = t.cpu()

    # Return Estimate as Numpy Float
    y = t.data.numpy()

    return y

  def eval(self, base_truth, meta_batch_size, gradient_steps, inner_step_size):

    # Sample Points from Task Sample Space
    x, y = sample_points(base_truth, self.meta_batch_size)

    # Model Base Estimate over Sample Space
    estimate = [self.predict(sample_space[:,None])]

    # Store Meta-Initialization Weights
    meta_weights = deepcopy(self.model.state_dict())

    # Get Estimate Loss over Meta-Initialization
    loss_t = self.loss(x,y).cpu()
    meta_loss = loss_t.data.numpy()

    # Calculcate Estimate over Gradient Steps
    for step in range(gradient_steps):

      # Calculate Evaluation Loss and Backpropagate
      eval_loss = self.loss(x,y)
      eval_loss.backward()

      # Update Model Estimate Parameters
      for theta in self.model.parameters():

        # Get Parameter Gradient
        grad = theta.grad.data

        # Update Model Parameter
        theta.data -= self.inner_step_size * grad

      # Update Estimate over Sample Space
      estimate.append(self.predict(sample_space[:, None]))

    # Get Estimate Loss over Evaluation
    loss_t = self.loss(x,y).cpu()
    estimate_loss = loss_t.data.numpy()
    evaluation_loss = abs(meta_loss - estimate_loss)/meta_batch_size
    
    # Restore Meta-Initialization Weights
    self.model.load_state_dict(meta_weights)

    return estimate, evaluation_loss

"""#### PyTorch Module"""

class TorchModule(nn.Module):

  def __init__(self, n):

    # Initialize PyTorch Base Module
    super(TorchModule, self).__init__()

    # Define Multi-Layer Perceptron
    self.input = nn.Linear(1,n)
    self.hidden_in = nn.Linear(n,n)
    self.hidden_out = nn.Linear(n,n)
    self.output = nn.Linear(n,1)

  def forward(self, x):

    # PyTorch Feed Forward Subroutine
    x = torch.tanh(self.input(x))
    x = torch.tanh(self.hidden_in(x))
    x = torch.tanh(self.hidden_out(x))
    y = self.output(x)

    return y

"""### Learning Task

#### Task Definition
"""

def logistic(x, theta):

  return theta[0] / (1 + np.exp(-1 * theta[1] * ( x - theta[2])))

"""#### Task Sampler"""

def sample(task):

  if task is not logistic:

    raise NotImplementedError

  # Parametric Generator for Logistic Regression Task (TODO: Generalize for Task - Parameter Specification)
  theta = [np.random.uniform( 1, 10), 
           np.random.uniform( 1, 10),
           np.random.uniform(-1,  1)]

  return task(sample_space, theta), theta

def sample_points(task, batch_size):

  # Sample Random Points from Sample Space
  idx = np.random.choice(np.arange(len(sample_space)), batch_size, replace = False)
  return sample_space[idx[:,None]], task[idx[:,None]]

def meta_sample(radius, count):

  # Generate Sample Space of Specified Radius
  sample_space = np.linspace(-radius, radius, count)
  return sample_space

"""## Experiments"""

# Define Experiment Parameters
inner_step_size = 0.02
inner_batch_size = 5

outer_step_size = 0.1
outer_iterations = 1000
meta_batch_size = 10

eval_iterations = 32
eval_batch_size = 10
eval_range = range(1,11)

model_size = 32
sample_radius = 4
sample_count = 100

params = [inner_step_size, inner_batch_size,
          outer_step_size, outer_iterations, meta_batch_size,
          eval_iterations, eval_batch_size]

# Define Experiment Task and Model
task = logistic
log = SummaryWriter(data_folder)
model = Reptile(TorchModule(model_size), log, params)

# Train Model
eval_mse = np.empty(shape=[len(eval_range), eval_batch_size])
sample_space = meta_sample(sample_radius, sample_count)
model.train(task)

# Evaluate Model
for batch in range(eval_batch_size):

  samples, task_theta  = sample(task)

  for sample_size in eval_range:

    # Estimate Model for Batch
    estimate, loss = model.eval(samples, sample_size, eval_iterations, inner_step_size)
    eval_mse[sample_size-1, batch-1] = loss
    
    # Log Results to Tensorboard
    for idx in range(len(samples)):
        log.add_scalars('Model Evaluation {}/{} Samples'.format(batch + 1, sample_size), 
            {'Task': samples[idx], 
              'Baseline': estimate[0][idx][0], 
              'Estimate' : estimate[-1][idx][0]}, 
              idx)

log.close()
print(eval_mse.mean(axis=1)[:,None])

"""### Results"""

# Commented out IPython magic to ensure Python compatibility.
# %load_ext tensorboard
# %reload_ext tensorboard
# %tensorboard --logdir /content/data
