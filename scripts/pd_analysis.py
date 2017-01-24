#!/usr/bin/env python
# -*- coding: UTF-8 -*-
import os
import imp
import shutil
import argparse
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use('Agg')
import warnings

try:
    import cPickle as pkl
except:
    import pickle as pkl

# from sklearn.metrics import accuracy_score, precision_recall_fscore_support
# from sklearn.metrics import matthews_corrcoef
from palladio import plotting
from palladio.metrics import (accuracy_score, precision_recall_fscore_support,
                              matthews_corrcoef, balanced_accuracy)

EXPS = ('regular', 'permutation')


def single_analysis(exp_folder, is_multiclass=False):
    """Perform the analysis on a single folder."""
    with open(os.path.join(exp_folder, 'result.pkl'), 'r') as f:
        result = pkl.load(f)

    y_true = result['labels_ts']  # the actual labels
    y_pred = result['prediction_ts_list']

    analysis = {
        'accuracy': accuracy_score(y_true, y_pred),
        'balanced_accuracy': balanced_accuracy(y_true, y_pred),
        'MCC': matthews_corrcoef(y_true, y_pred) if not is_multiclass
        else None
    }
    analysis['precision'], analysis['recall'], analysis['F1'], _ = \
        precision_recall_fscore_support(y_true, y_pred, average='weighted')

    # save selected_list
    analysis['selected_list'] = result['selected_list']

    # save kcv errors
    analysis['kcv_err_ts'] = result['kcv_err_ts']
    analysis['kcv_err_tr'] = result['kcv_err_tr']
    return analysis


def analyze_experiments(base_folder, config):
    """Perform a preliminar analysis on all experiments.

    Produce a summary for each experiment that will be used for
    aggregate analysis.

    Parameters
    ----------
    base_folder : string
        Folder containing ALL experiments (regular and permutations).
    """
    # Local imports, in order to select backend on startup
    dataset = config.dataset_class(
        config.dataset_files,
        config.dataset_options,
        is_analysis=True
    )

    # ### FIN QUI

    features = np.array(dataset.load_dataset(base_folder)[2])

    print("Features : {}".format(features))

    return



    out = dict()
    for s in EXPS:
        out['selected_%s' % s] = dict(zip(features, np.zeros(len(features))))
        out['kcv_err_%s' % s] = {'tr': list(), 'ts': list()}

    experiments_folder = os.path.join(base_folder, 'experiments')
    for exp_folder in os.listdir(experiments_folder):
        exp_folder = os.path.join(experiments_folder, exp_folder)
        if os.path.isdir(exp_folder):
            filename = exp_folder.split('/')[-1]
            if not filename.startswith(EXPS[0]) and \
                    not filename.startswith(EXPS[1]):
                print('error')
                continue

            analysis_result = single_analysis(exp_folder, dataset.multiclass)

            selected_probesets = features[analysis_result['selected_list']]
            is_regular = filename.startswith(EXPS[0])
            type_experiment = EXPS[0] if is_regular else EXPS[1]
            for p in selected_probesets.flatten():
                out['selected_%s' % type_experiment][p] += 1

            out['kcv_err_%s' % type_experiment]['tr'].append(
                analysis_result['kcv_err_tr'])
            out['kcv_err_%s' % type_experiment]['ts'].append(
                analysis_result['kcv_err_ts'])

            out.setdefault('F1_%s' % type_experiment, []).append(
                analysis_result['F1'])
            out.setdefault('acc_%s' % type_experiment, []).append(
                analysis_result['accuracy'])
            out.setdefault('balanced_acc_%s' % type_experiment, []).append(
                analysis_result['balanced_accuracy'])
            out.setdefault('MCC_%s' % type_experiment, []).append(
                analysis_result['MCC'])
            out.setdefault('precision_%s' % type_experiment, []).append(
                analysis_result['precision'])
            out.setdefault('recall_%s' % type_experiment, []).append(
                analysis_result['recall'])

    for s in EXPS:
        out['F1_%s' % s] = np.array(out['F1_%s' % s])
        out['acc_%s' % s] = np.array(out['acc_%s' % s])
        out['balanced_acc_%s' % s] = np.array(out['balanced_acc_%s' % s])
        out['MCC_%s' % s] = np.array(out['MCC_%s' % s])
        out['precision_%s' % s] = np.array(out['precision_%s' % s])
        out['recall_%s' % s] = np.array(out['recall_%s' % s])

    return out


def main(base_folder):
    """Main for pd_analysis.py."""
    config = imp.load_source('config', os.path.join(base_folder, 'config.py'))



    positive_label = config.dataset_options.get('positive_label', None)
    multiclass = config.dataset_options.get('multiclass', None)


    # print("PL = {}".format(positive_label))
    # print("multiclass = {}".format(multiclass))

    threshold = int(config.N_jobs_regular * config.frequency_threshold)

    # TODO necessary?
    param_names = list(config.param_grid.keys())
    param_ranges = [config.param_grid[x] for x in param_names]

    # ### FIN QUI

    out = analyze_experiments(base_folder, config)

    return







    # create a new folder for the analysis, called 'analysis'
    base_folder = os.path.join(base_folder, 'analysis')
    if not os.path.exists(base_folder):
        os.makedirs(base_folder)

    # firstly, if exists, copy there the report.txt
    shutil.copy(
        os.path.abspath(os.path.join(base_folder, os.pardir, 'report.txt')),
        base_folder)

    # Manually sorting stuff
    for s in EXPS:
        out['sorted_keys_%s' % s] = sorted(
            out['selected_%s' % s], key=out['selected_%s' % s].__getitem__)

    selected_todf = [out['selected_regular'][k] for k in out['sorted_keys_regular']]
    # Dump the selected features in a pkl as pandas DataFrame
    df_selected = pd.DataFrame(
        data=selected_todf, index=out['sorted_keys_regular'],
        columns=['Selection frequency'])
    df_selected.sort_values(['Selection frequency'], ascending=False,
                            inplace=True)
    df_selected.to_pickle(os.path.join(base_folder, 'signature_regular.pkl'))

    for s in EXPS:
        with open(os.path.join(base_folder, 'signature_%s.txt' % s), 'w') as f:
            line_drawn = False
            for k in reversed(out['sorted_keys_%s' % s]):
                if not line_drawn and out['selected_%s' % s][k] < threshold:
                    line_drawn = True
                    f.write("=" * 40)
                    f.write("\n")
                f.write("{} : {}\n".format(k, out['selected_%s' % s][k]))

    # Plotting section
    plotting.distributions(out['acc_regular'], out['acc_permutation'],
                           base_folder, 'Accuracy', first_run=True)
    plotting.distributions(
        out['balanced_acc_regular'], out['balanced_acc_permutation'],
        base_folder, 'Balanced Accuracy')
    plotting.distributions(out['MCC_regular'], out['MCC_permutation'],
                           base_folder, 'MCC')
    if positive_label is not None and not multiclass:
        plotting.distributions(out['precision_regular'],
                               out['precision_permutation'],
                               base_folder, 'Precision')
        plotting.distributions(
            out['recall_regular'], out['recall_permutation'], base_folder,
            'Recall')
        plotting.distributions(out['F1_regular'], out['F1_permutation'],
                               base_folder, 'F1')

    plotting.feature_frequencies(
        out['sorted_keys_regular'], out['selected_regular'], base_folder,
        threshold=threshold)

    plotting.features_manhattan(
        out['sorted_keys_regular'], out['selected_regular'],
        out['selected_permutation'], base_folder, config.N_jobs_regular,
        config.N_jobs_permutation, threshold=threshold)

    plotting.selected_over_threshold(
        out['selected_regular'], out['selected_permutation'],
        config.N_jobs_regular, config.N_jobs_permutation, base_folder,
        threshold=threshold)
    if len(param_ranges) != 2:
        warnings.warn("Length of param_ranges is not 2. "
                      "Cannot produce surfaces")
    else:
        for s in EXPS:
            plotting.kcv_err_surfaces(
                out['kcv_err_%s' % s], s, base_folder, param_ranges,
                param_names)


def parse_args():
    """Parse arguments."""
    from palladio import __version__
    parser = argparse.ArgumentParser(
        description='palladio script for analysing results.')
    parser.add_argument('--version', action='version',
                        version='%(prog)s v' + __version__)
    parser.add_argument("result_folder", help="specify results directory")
    return parser.parse_args()


if __name__ == '__main__':
    main(parse_args().result_folder)
