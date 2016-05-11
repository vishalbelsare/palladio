#!/usr/bin/python -u
# -*- coding: utf-8 -*-
import os, sys
import imp
import shutil
import cPickle as pkl
import random

import time

import numpy as np

from mpi4py import MPI

from palladio.wrappers.l1l2 import l1l2Classifier
from l1l2signature import utils as l1l2_utils

from palladio.utils import sec_to_timestring

### Initialize MPI variables
### THESE ARE GLOBALS
comm = MPI.COMM_WORLD
size = comm.Get_size()
rank = comm.Get_rank()
name = MPI.Get_processor_name()

def generate_job_list(N_jobs_regular, N_jobs_permutation):
    """
    Given the total number of processes, generate a list of jobs distributing the load,
    so that each process has approximately the same amount of work to do
    (i.e., the same number of regular and permutated instances of the experiment)
    """
    
    # The total number of jobs
    N_jobs_total = N_jobs_permutation + N_jobs_regular
    
    # A vector representing the type of experiment: 1 for permutation, 0 for regular
    type_vector = np.ones((N_jobs_total,))
    type_vector[N_jobs_permutation:] = 0
    np.random.shuffle(type_vector)
    
    return type_vector

def run_experiment(data, labels, config_dir, config, is_permutation_test, custom_name):
    
    result_path = os.path.join(config_dir, config.result_path) #result base dir
    
    ### Create experiment folders
    result_dir = os.path.join(result_path, custom_name)
    os.mkdir(result_dir)
    
    ### Split the dataset in learning and test set
    ### Use a trick to keep the original splitting strategy
    aux_splits = config.cv_splitting(labels, int(round(1/(config.test_set_ratio))), rseed = None)
    
    idx_lr = aux_splits[0][0]
    idx_ts = aux_splits[0][1]
    
    data_lr = data[idx_lr, :]
    labels_lr = labels[idx_lr]
    
    data_ts = data[idx_ts, :]
    labels_ts = labels[idx_ts]
    
    ### Compute the ranges of the parameters using only the learning set
    ### TODO FIX
    if is_permutation_test:
        labels_perm = labels_lr.copy()
        np.random.shuffle(labels_perm)
        
    Xtr = data_lr
    Ytr = labels_perm if is_permutation_test else labels_lr
    Xts = data_ts
    Yts = labels_ts

    int_k = config.internal_k
    ms_split = config.cv_splitting(Ytr, int_k) # args[3]=k -> splits
    
    sparse, regularized, return_predictions = (True, False, True)
    
    params = {
        'mu_range' : config.mu_range,
        'tau_range' : config.tau_range,
        'lambda_range' : config.lambda_range,
        'data_normalizer' : config.data_normalizer,
        'ms_split' : ms_split,
        'cv_error' : config.cv_error,
        'error' : config.error,
        'labels_normalizer' : config.labels_normalizer,
        'sparse' : sparse,
        'regularized' : regularized,
        'return_predictions' : return_predictions
    }

    ### Create the object that will actually perform the classification/feature selection
    clf = l1l2Classifier(params)
    
    ### Set the actual data and perform additional steps such as rescaling parameters etc.
    clf.setup(Xtr, Ytr, Xts, Yts)
    
    result = clf.run()

    # result = out['result']
    result['labels_ts'] = labels_ts ### also save labels
    
    # save results 
    with open(os.path.join(result_dir, 'result.pkl'), 'w') as f:
        pkl.dump(result, f, pkl.HIGHEST_PROTOCOL)
        
    in_split = {
        'ms_split': ms_split,
        'outer_split': aux_splits[0]
    }
        
    with open(os.path.join(result_dir, 'in_split.pkl'), 'w') as f:
        pkl.dump(in_split, f, pkl.HIGHEST_PROTOCOL)
    
    return
    
    
# def main(config_path, custom_name = None):
def main(config_path):
    
    if rank == 0:
        t0 = time.time()
    
    # Configuration File
    config_dir = os.path.dirname(config_path)

    imp.acquire_lock()
    config = imp.load_source('config', config_path)
    imp.release_lock()
    
    # Data paths
    data_path = os.path.join(config_dir, config.data_matrix)
    labels_path = os.path.join(config_dir, config.labels)
    
    ### Create base results dir if it does not already exist
    if rank == 0:
        result_path = os.path.join(config_dir, config.result_path) #result base dir
        if not os.path.exists(result_path):
            os.mkdir(result_path)
            
        shutil.copy(config_path, os.path.join(result_path, 'config.py'))
        os.link(data_path, os.path.join(result_path, 'data_file'))
        os.link(labels_path, os.path.join(result_path, 'labels_file'))
        
            
    ### Wait for the folder to be created and files to be copied
    comm.barrier()
    
    # Experimental design
    N_jobs_regular = config.N_jobs_regular
    N_jobs_permutation = config.N_jobs_permutation
    
    if rank == 0:
        print("") #--------------------------------------------------------------------
        print('Reading data... ')
        
    br = l1l2_utils.BioDataReader(data_path, labels_path,
                                  config.sample_remover,
                                  config.variable_remover,
                                  config.delimiter,
                                  config.samples_on,
                                  config.positive_label)
    data = br.data
    labels = br.labels

    if rank == 0:
        print('  * Data shape:', data.shape)
        print('  * Labels shape:', labels.shape)
        
    if rank == 0:
        job_list = generate_job_list(N_jobs_regular, N_jobs_permutation)
    else:
        job_list = None
    
    ### Distribute job list with broadcast
    job_list = comm.bcast(job_list, root=0)
    
    ### Compute which jobs each process has to handle
    N_jobs_total = N_jobs_permutation + N_jobs_regular
    
    jobs_per_proc = N_jobs_total/size
    exceeding_jobs = N_jobs_total%size
    
    ### compute the local offset
    heavy_jobs = min(rank, exceeding_jobs) # jobs that make one extra iteration
    light_jobs = rank - heavy_jobs
    offset = heavy_jobs*(jobs_per_proc + 1) + light_jobs*jobs_per_proc
    idx = np.arange(offset, offset + jobs_per_proc + int(rank < exceeding_jobs))
    
    ### The jobs handled by this process
    local_jobs = job_list[idx]
    
    # print("Job {}, handling jobs {}".format(rank, idx))
    
    for i, is_permutation_test in enumerate([bool(x) for x in local_jobs]):
        
        # print("Job {}, is permutation test? {}".format(rank, is_permutation_test))
        
        ### Create a custom name for the experiment based on whether it is a permutation test,
        ### the process' rank and a sequential number
        custom_name = "{}_p_{}_i_{}".format(("permutation" if is_permutation_test else "regular"), rank, i)
        
        run_experiment(data, labels, config_dir, config, is_permutation_test, custom_name)
        
        print("[{}_{}] finished experiment {}".format(name, rank, i))
        
        
    if rank == 0:
        t100 = time.time()
        
    if rank == 0:
        
        with open(os.path.join(result_path, 'report.txt'), 'w') as rf:
            
            rf.write("Total elapsed time: {}".format(sec_to_timestring(t100-t0)))
        
    return    

# Script entry ----------------------------------------------------------------
if __name__ == '__main__':
    
    # main2()
    
    if len(sys.argv) != 2:
        print('incorrect number of arguments')
    config_file_path = sys.argv[1]
    
    main(os.path.abspath(config_file_path))