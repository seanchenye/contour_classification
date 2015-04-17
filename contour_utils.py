""" Utility functions for processing contours """

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
sns.set()
import mir_eval

def load_contour_data(fpath):
    """ Load contour data from vamp output csv file.

    Parameters
    ----------
    fpath : str
        Path to vamp output csv file.

    Returns
    -------
    contour_data : DataFrame
        Pandas data frame with all contour data.
    """
    contour_data = pd.read_csv(fpath, header=None, index_col=None,
                               delimiter=',')
    del contour_data[0]  # all zeros
    del contour_data[1]  # just an unnecessary  index
    headers = contour_data.columns.values.astype('str')
    headers[0:12] = ['onset', 'offset', 'duration', 'pitch mean', 'pitch std',
                     'salience mean', 'salience std', 'salience tot',
                     'vibrato', 'vib rate', 'vib extent', 'vib coverage']
    contour_data.columns = headers
    return contour_data


def features_from_contour_data(contour_data, normalize=True):
    """ Get subset of columns corresponding to features.
    Adds labels column with all labels unset.

    Parameters
    ----------
    contour_data : DataFrame
        Pandas data frame with all contour data.
    normalize : Bool
        If true, performs trackwise normalization over salience.

    Returns
    -------
    features : DataFrame
        Pandas data frame with contour feature data.
    """
    features = contour_data.iloc[:, 2:12]
    if normalize:
        _, _, contour_sal = contours_from_contour_data(contour_data)

        #maximum salience value across all contours
        sal_max = contour_sal.max().max()

        # normalize salience features by max salience
        features['salience mean'] = features['salience mean']/sal_max
        features['salience std'] = features['salience std']/sal_max

        # normalize saience total by max salience and duration
        features['salience tot'] = \
            features['salience tot']/(sal_max*features['duration'])

        # compute min and max duration
        dur_min = features['duration'].min()
        dur_max = features['duration'].max()

        # normalize duration to be between 0 and 1
        features['duration'] = \
            (features['duration'] - dur_min)/(dur_max - dur_min)

        # give standardized duration back to total salience
        features['salience tot'] = \
            features['salience tot']*features['duration']

    features['labels'] = -1  # all labels are unset
    features['overlap'] = -1 # overlaps are unset
    return features


def contours_from_contour_data(contour_data):
    """ Get raw contour information from contour data

    Parameters
    ----------
    contour_data : DataFrame
        Pandas data frame with all contour data.

    Returns
    -------
    contour_times : DataFrame
        Pandas data frame with all raw contour times.
    contour_freqs : DataFrame
        Pandas data frame with all raw contour frequencies (Hz).
    contour_sal : DataFrame
        Pandas data frame with all raw contour salience values.
    """
    contours = contour_data.iloc[:, 12:]
    contour_times = contours.iloc[:, 0::3]
    contour_freqs = contours.iloc[:, 1::3]
    contour_sal = contours.iloc[:, 2::3]

    return contour_times, contour_freqs, contour_sal

def load_annotation(fpath):
    """ Load an annotation file into a pandas Series.
    Add column with frequency values also converted to cents.

    Parameters
    ----------
    fpath : str
        Path to annotation file.

    Returns
    -------
    annot_data : DataFrame
        Pandas data frame with all annotation data.
    """
    annot_data = pd.read_csv(fpath, parse_dates=True,
                             index_col=False, header=None)
    annot_data.columns = ['time', 'f0']

    # Add column with annotation values in cents
    annot_data['cents'] = 1200.0*np.log2(annot_data['f0']/55.0)

    return annot_data


def make_coverage_plot(contour_data, annot_data, contour_data2=None):
    """ Plot contours against annotation.

    Parameters
    ----------
    contour_data : DataFrame
        Pandas data frame with all contour data.
    annot_data : DataFrame
        Pandas data frame with all annotation data.
    """
    if contour_data2 is not None:
        c_times2, c_freqs2, _ = contours_from_contour_data(contour_data2)
        for (times, freqs) in zip(c_times2.iterrows(), c_freqs2.iterrows()):
            times = times[1].values
            freqs = freqs[1].values
            times = times[~np.isnan(times)]
            freqs = freqs[~np.isnan(freqs)]
            plt.plot(times, freqs, '.c', zorder=1)

    c_times, c_freqs, _ = contours_from_contour_data(contour_data)
    plt.figure()
    for (times, freqs) in zip(c_times.iterrows(), c_freqs.iterrows()):
        times = times[1].values
        freqs = freqs[1].values
        times = times[~np.isnan(times)]
        freqs = freqs[~np.isnan(freqs)]
        plt.plot(times, freqs, '.r', zorder=2)

    plt.plot(annot_data['time'], annot_data['f0'], '+k', zorder=3)
    plt.show()


def contour_overlap(contour_data, annot_data):
    """ Compute percentage of overlap of each contour with annotation.

    Parameters
    ----------
    contour_data : DataFrame
        Pandas data frame with all contour data.
    annot_data : DataFrame
        Pandas data frame with all annotation data.

    Returns
    -------
    feature_data : DataFrame
        Pandas data frame with feature_data and labels.
    """
    c_times, c_freqs, _ = contours_from_contour_data(contour_data)
    feature_data = features_from_contour_data(contour_data)

    for (times, freqs) in zip(c_times.iterrows(), c_freqs.iterrows()):
        row_idx = times[0]
        times = times[1].values
        freqs = freqs[1].values

        # remove trailing NaNs
        times = times[~np.isnan(times)]
        freqs = freqs[~np.isnan(freqs)]

        # get segment of ground truth matching this contour
        gt_segment = annot_data[annot_data['time'] >= times[0]]
        gt_segment = gt_segment[gt_segment['time'] <= times[-1]]

        # compute metrics
        res = mir_eval.melody.evaluate(gt_segment['time'].values,
                                       gt_segment['f0'].values, times, freqs)

        feature_data.ix[row_idx, 'overlap'] = res['Overall Accuracy']

    return feature_data


def label_contours(feature_data, olap_thresh):
    """ Compute contours based on annotation.
    Contours with at least olap_thresh overlap with annotation
    are labeled as positive examples. Otherwise negative.

    Parameters
    ----------
    contour_data : DataFrame
        Pandas data frame with all contour data.
    annot_data : DataFrame
        Pandas data frame with all annotation data.
    olap_thresh : float
        Overlap threshold for positive examples

    Returns
    -------
    feature_data : DataFrame
        Pandas data frame with feature_data and labels.
    """
    feature_data['labels'] = 1*(feature_data['overlap'] > olap_thresh)
    return feature_data


def find_overlapping_contours(contour_data, annot_data):
    """ Get subset of contour data that overlaps with annotation.

    Parameters
    ----------
    contour_data : DataFrame
        Pandas data frame with all contour data.
    annot_data : DataFrame
        Pandas data frame with all annotation data.

    Returns
    -------
    olap_contours : DataFrame
        Subset of contour_data that overlaps with annotation.
    """
    olap_contours = contour_data.copy()

    c_times, c_freqs, _ = contours_from_contour_data(contour_data)

    for (times, freqs) in zip(c_times.iterrows(), c_freqs.iterrows()):
        row_idx = times[0]
        times = times[1].values
        freqs = freqs[1].values

        # remove trailing NaNs
        times = times[~np.isnan(times)]
        freqs = freqs[~np.isnan(freqs)]

        # get segment of ground truth matching this contour
        gt_segment = annot_data[annot_data['time'] >= times[0]]
        gt_segment = gt_segment[gt_segment['Time'] <= times[-1]]

        # compute metrics
        res = mir_eval.melody.evaluate(gt_segment['time'].values, \
                                       gt_segment['f0'].values, times, freqs)
        if res['Raw Pitch Accuracy'] == 0:
            olap_contours.drop(row_idx, inplace=True)

    return olap_contours

def join_features(features_list):
    """ Merge features for a multiple track into a single DataFrame

    Parameters
    ----------
    features_list : list of DataFrames
        List of Pandas data frames with labeled features.

    Returns
    -------
    all_features : DataFrame
        Merged feature data.
    """
    all_features = pd.concat(features_list, ignore_index=False)
    return all_features


def pd_to_sklearn(features):
    """ Convert pandas data frame to sklearn style features and labels 

    Parameters
    ----------
    features : DataFrame
        DataFrame containing labeled features.

    Returns
    -------
    X : np.ndarray
        fetures (n_samples x n_features)
    Y : np.1darray
        Labels (n_samples,)
    """
    X = np.array(features.iloc[:, 0:10])
    Y = np.array(features['labels'])
    return X, Y


