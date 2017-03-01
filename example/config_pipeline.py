# Configuration file example for PALLADIO
# version: 2.0

import numpy as np

from sklearn.linear_model import RidgeClassifier
from sklearn.feature_selection import SelectKBest
from sklearn.pipeline import make_pipeline

from palladio.datasets import DatasetCSV as dataset_class
# from palladio.datasets import DatasetNPY as dataset_class

#####################
#   DATASET PATHS ###
#####################

# * All the path are w.r.t. config file path

# The list of all files required for the experiments
dataset_files = {
    'data': 'data/gedm.csv',
    'labels': 'data/labels.csv'
}

dataset_options = {
    'positive_label': 'ALL',  # Indicates the positive class in case of 2-class task
    'samples_on': 'col',  # or 'row': samples on cols or rows
    # 'data_preprocessing' : None,

    # other options for pandas.read_csv
    'delimiter': ',',
    'header': 0,
    'index_col': 0
}

# # The list of all files required for the experiments
# dataset_files = {
#     'data': 'data/iris_data.npy',
#     'labels': 'data/iris_labels.npy',
#     'indcol': 'data/iris_indcols.pkl'
# }
#
# dataset_options = {
#     'samples_on': 'row',  # or 'row': samples on cols or rows
#     'positive_label': 1,  # positive class in case of 2-class task
# }

#######################
#   SESSION OPTIONS ###
#######################

result_path = 'palladio_test_golub_pipeline'

# The number of "regular" experiment
N_jobs_regular = 20

# The number of instances for the permutation tests
# (labels in the training sets are randomly shuffled)
N_jobs_permutation = 20

# The ratio of the dataset held out for model assessment
# It should be of the form 1/M
test_set_ratio = float(1) / 4

#######################
#  LEARNER OPTIONS  ###
#######################

estimator = make_pipeline(SelectKBest(), RidgeClassifier())

# Parameter grid for both steps
# make_pipeline as default puts the lowercase name of the classes as names
param_grid = {
    'selectkbest__k': [1, 3, 5, 10],
    'ridgeclassifier__alpha': np.logspace(-4, 2, 5),
}

# ~~ Cross validation options ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
cv_options = {
    'param_grid': param_grid,
    'cv': 3,
    'scoring': 'accuracy',
}

final_scoring = 'accuracy'

# For the Pipeline object, indicate the name of the step from which to
# retrieve the list of selected features
# For a single estimator which has a `coef_` attributes (e.g., elastic net or
# lasso) set to True
vs_analysis = 'selectkbest'

# ~~ Signature Parameters ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
frequency_threshold = 0.75