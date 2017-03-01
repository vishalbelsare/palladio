#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Palladio script for summaries and plot generation."""

import argparse
import imp
import numpy as np
import os

from six.moves import cPickle as pkl
from six.moves import filter
from sklearn.base import is_regressor
from sklearn.utils.multiclass import type_of_target

from palladio import plotting
from palladio.metrics import __REGRESSION_METRICS__
from palladio.metrics import __CLASSIFICATION_METRICS__
from palladio.utils import build_cv_results
from palladio.utils import get_selected_list
from palladio.utils import save_signature


def regression_analysis(cv_results, config):
    """Evaluate the regression metrics on the external splits results.

    Parameters
    ----------
    cv_results : dictionary
        As in `palladio.ModelAssessment.cv_results_`
    config : module
        Palladio config of the current experiment

    Returns
    -------
    performance_metrics : dictionary
        Regression metrics evaluated on the external splits results
    """
    test_index = cv_results['test_index']
    yts_pred = cv_results['yts_pred']
    yts_true = [config.labels[i] for i in test_index]

    # Evaluate all the metrics on the results
    performance_metrics = {}
    for metric in __REGRESSION_METRICS__:
        performance_metrics[metric.__name__] = [
            metric(*yy) for yy in zip(yts_true, yts_pred)]

    return performance_metrics


def classification_analysis(cv_results, config):
    """Evaluate the classification metrics on the external splits results.

    Parameters
    ----------
    cv_results : dictionary
        As in `palladio.ModelAssessment.cv_results_`
    config : module
        Palladio config of the current experiment

    Returns
    -------
    performance_metrics : dictionary
        Regression metrics evaluated on the external splits results
    """
    test_index = cv_results['test_index']
    yts_pred = cv_results['yts_pred']
    yts_true = [config.labels[i] for i in test_index]

    # Evaluate all the metrics on the results
    performance_metrics = {}
    for metric in __CLASSIFICATION_METRICS__:
        performance_metrics[metric.__name__] = [
            metric(*yy) for yy in zip(yts_true, yts_pred)]

    return performance_metrics


def load_results(base_folder):
    """Load pd_run.py results in pickle format.

    Parameters
    ----------
    base_folder : string
        Folder containing ALL experiments (regular and permutations).

    Returns
    -------
    regular_cv_results : dictionary
        As in `palladio.ModelAssessment.cv_results_`
    permutation_cv_results : dictionary
        As in `palladio.ModelAssessment.cv_results_`
    """
    experiments_folder = os.path.join(base_folder, 'experiments')
    pkls = [f for f in os.listdir(experiments_folder) if f.endswith('.pkl')]
    assert(len(pkls) > 0), "no pkl files found in %s" % base_folder

    # Separate regular VS permutation batches
    regular_batch = filter(lambda x: 'regular' in x, pkls)
    permutation_batch = filter(lambda x: 'permutation' in x, pkls)

    # Regular batch
    regular_cv_results = {}  # dictionary of results as in ModelAssessment
    for pkl_file in regular_batch:
        row = pkl.load(open(os.path.join(experiments_folder, pkl_file), 'rb'))
        build_cv_results(regular_cv_results, **row)

    # Regular batch
    permutation_cv_results = {}  # dictionary of results as in ModelAssessment
    for pkl_file in permutation_batch:
        row = pkl.load(open(os.path.join(experiments_folder, pkl_file), 'rb'))
        build_cv_results(permutation_cv_results, **row)

    return regular_cv_results, permutation_cv_results


def main():
    """Summary and plot generation."""
    parser = parse_args()
    base_folder = parser.result_folder
    config = imp.load_source('config', os.path.join(base_folder, 'config.py'))

    # Load results from pkl
    regular_cv_results, permutation_cv_results = load_results(base_folder)

    # Get feature names
    if hasattr(config, 'feature_names'):
        feature_names = config.feature_names
    else:  # the following code creates [feat_0, feat_1, ..., feat_d]
        feature_names = 'feat_' + np.arange(
            config.data.shape[1]).astype(str).astype(object)

    # learning_task follows the convention of
    # sklearn.utils.multiclass.type_of_target
    learning_task = config.learning_task if hasattr(config, 'learning_task') \
        else None
    if learning_task is None:
        if is_regressor(config.estimator):
            learning_task = 'continuous'
        else:
            learning_task = type_of_target(config.labels)

    # Run the appropriate analysis according to the learning_task
    if learning_task.lower() in ['continuous', 'regression']:
        # Perform regression analysis
        performance_regular = regression_analysis(regular_cv_results, config)
        performance_permutation = {}  # for consistency only
    else:
        # Perform classification analysis
        performance_regular = classification_analysis(
            regular_cv_results, config)
        performance_permutation = classification_analysis(
            permutation_cv_results, config)

    # Handle variable selection step
    if config.vs_analysis is not None:
        threshold = config.frequency_threshold if hasattr(
             config, 'frequency_threshold') else .75
        if threshold is None:
            threshold = .75
        selected = {}
        # Init variable selection containers
        selected['regular'] = dict(zip(feature_names,
                                       np.zeros(len(feature_names))))
        selected['permutation'] = selected['regular'].copy()

        n_jobs = {'regular': config.N_jobs_regular,
                  'permutation': config.N_jobs_permutation}
        names_ = ('regular', 'permutation')
        cv_results_ = (regular_cv_results, permutation_cv_results)
        for batch_name, cv_result in zip(names_, cv_results_):
            # cv_result['estimator'] is a list containing
            # the grid-search estimators
            estimators = cv_result.get('estimator', None)
            if estimators is None:
                continue  # in case of no permutations skip this iter
            for estimator in estimators:
                selected_list = get_selected_list(
                    estimator, config.vs_analysis)
                selected_variables = feature_names[selected_list]

                for var in selected_variables:
                    selected[batch_name][var] += 1. / n_jobs[batch_name]

            # Save selected variables textual summary
            filename = os.path.join(
                base_folder, 'signature_%s.txt' % batch_name)
            save_signature(filename, selected[batch_name], threshold)

        sorted_keys_regular = sorted(
            selected['regular'], key=selected['regular'].__getitem__)

        # # Save graphical summary
        plotting.feature_frequencies(
            sorted_keys_regular, selected['regular'], base_folder,
            threshold=threshold)

        plotting.features_manhattan(
            sorted_keys_regular, selected['regular'],
            selected['permutation'], base_folder,
            threshold=threshold)

        plotting.selected_over_threshold(
            selected['regular'], selected['permutation'],
            base_folder, threshold=threshold)

    # Generate distribution plots
    first_run = True
    for metric in performance_regular:
        plotting.distributions(v_regular=performance_regular[metric],
                               v_permutation=performance_permutation.get(metric, []),
                               base_folder=base_folder, metric=metric,
                               first_run=first_run,
                               is_regression=learning_task.lower() in ['continuous', 'regression'])
        if first_run:
            first_run = False

    # Generate surfaces
    plotting.score_surfaces(param_grid=config.param_grid,
                            results=regular_cv_results,
                            indep_var=config.indep_vars if hasattr(
                                config, 'indep_vars') else None,
                            pivoting_var=config.pivot_var if hasattr(
                                config, 'pivot_var') else None,
                            base_folder=base_folder,
                            logspace=config.logspace if hasattr(
                                config, 'logspace') else None,
                            plot_errors=config.plot_errors if hasattr(
                                config, 'plot_errors') else False,
                            is_regression=learning_task.lower() in ['continuous', 'regression'])


def parse_args():
    """Parse arguments."""
    from palladio import __version__
    parser = argparse.ArgumentParser(
        description='palladio script for analysing results.')
    parser.add_argument('--version', action='version',
                        version='%(prog)s v' + __version__)
    parser.add_argument("-o", "--output", dest="output_folder", action="store",
                        help="specify a name for the analysis folder",
                        default='analysis')
    parser.add_argument("result_folder", help="specify results directory")
    return parser.parse_args()


if __name__ == '__main__':
    main()