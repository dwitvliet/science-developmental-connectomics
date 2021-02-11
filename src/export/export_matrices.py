import os
import random
import itertools
import collections

import numpy as np
import pandas as pd
import scipy.io

from src.data import data_manager
from src.data.neuron_info import neuron_list, in_brain, class_members, ntype, is_postemb


def export_synapses(path):
    df_to_store = fig_supplemental._synapses_on_branches(exclude_postemb=False, remove_unknown=False)[
        ['dataset', 'pre', 'post', 'syn_id', 'sections', 'size', 'post_is_branch']
    ]
    for col in ('size', ):
        df_to_store.loc[:, col] = df_to_store[col].fillna(-1).astype(int)
        
    df_to_store['post_is_branch'] = df_to_store['post_is_branch'].astype(str).replace({'True': 'yes', 'False': 'no'})
    valid_cells = set([n for c in neuron_list if in_brain(c) for n in class_members(c) if ntype(c) not in ('other', )])
    df_to_store.loc[~df_to_store['post'].isin(valid_cells), 'post_is_branch'] = 'unknown'

    fpath = os.path.join(path, 'synapse_list.csv')
    df_to_store.to_csv(fpath, index=False)
    print(f'Saved to `{fpath}`')


def export_classifications(path, pair_classifications):
    # Write edge classifications to file.
    G = data_manager.get_connections().copy()
    G_pair = data_manager.to_npair(G)
    G_pair['edge_classifications'] = 'post-embryonic brain integration'
    postemb_connections = G_pair[
        G_pair.index.map(lambda idx: is_postemb(idx[0]) or is_postemb(idx[1]))]

    classifications = pair_classifications.copy()

    classifications = classifications.append(
        postemb_connections['edge_classifications'],
        verify_integrity=True
    ) \
        .sort_index() \
        .replace('noise', 'variable') \
        .replace('remainder', 'variable') \
        .replace('stable', 'stable') \
        .replace('increase', 'developmentally dynamic (strengthened)') \
        .replace('decrease', 'developmentally dynamic (weakened)')

    classifications.name = 'classification'

    fpath = os.path.join(path, 'connection_classifications.csv')
    classifications.to_csv(fpath)
    print(f'Saved to `{fpath}`')


def export_to_excel(path):
    
    valid_neurons = set([n for c in neuron_list if in_brain(c) for n in class_members(c)])
    valid_pre = set([n for n in valid_neurons if ntype(n) not in ('muscle', 'other')])
    valid_post = valid_neurons
    no_adjacency = set([n for n in valid_neurons if ntype(n) == 'other'])
    added_pre = set()
    added_post = set()
    
    G = data_manager.get_connections().copy()
    G_adj = data_manager.get_adjacency().copy()
    
    dfs_to_export = {
        'synapse_count': G['count'],
        'synapse_size': G['size'],
        'contact': G_adj,
    }

    matrices = collections.defaultdict(dict)    
    for measure in dfs_to_export:
        for dataset in dfs_to_export[measure]:
            
            if dataset == 'Dataset7' and measure != 'synapse_count':
                continue
            
            matrix = dfs_to_export[measure] \
                .reset_index() \
                .pivot(columns='pre', index='post', values=dataset) \
                .fillna(0) \
                .astype(int)
            
            # Add/remove unexpected cells.
            if measure == 'contact':
                missing_pre = valid_neurons - no_adjacency - set(matrix.columns) 
                missing_post = valid_neurons - no_adjacency - set(matrix.index)
                invalid_pre = set(matrix.columns) - (valid_neurons - no_adjacency)
                invalid_post = set(matrix.index) - (valid_neurons - no_adjacency)
            else:
                missing_pre = valid_pre - set(matrix.columns)
                missing_post = valid_post - set(matrix.index)
                invalid_pre = set(matrix.columns) - valid_pre
                invalid_post = set(matrix.index) - valid_post
            for n in missing_pre:
                matrix[n] = 0
                added_pre.add(n)
            for n in missing_post:
                matrix.loc[n] = 0
                added_post.add(n)
            for n in invalid_pre:
                matrix = matrix.drop(n, axis=1)
            for n in invalid_post:
                matrix = matrix.drop(n, axis=0)
            
            # Sort by type, then name.
            type_index = {'sensory': 0, 'modulatory': 4, 'inter': 1, 'motor': 3, 'muscle': 5, 'other': 6}
            sort_key = lambda n: (type_index[ntype(n)], n.replace('BWM', n[6:8]+'BWM'))
            pre_sorted = sorted(matrix.columns, key=sort_key)
            post_sorted = sorted(matrix.index, key=sort_key)
            matrix = matrix.loc[post_sorted, pre_sorted]
            
            matrices[measure][dataset] = matrix

    # print('Added pre', added_pre)
    # print('Added post', added_post)
    
    for measure in matrices:
        fpath = os.path.join(path, f'{measure}_matrices.xlsx')
        with pd.ExcelWriter(fpath) as f:
            
            for dataset in matrices[measure]:
                
                matrix = matrices[measure][dataset]
                
                # Add indexes for export
                matrix.index = pd.MultiIndex.from_arrays(
                    [
                        ['Post']*len(matrix.index), 
                        [ntype(n).capitalize() for n in matrix.index],
                        matrix.index
                    ],
                    names=(None, None, None)
                )
                matrix.columns = pd.MultiIndex.from_arrays(
                    [
                        ['Pre']*len(matrix.columns), 
                        [ntype(n).capitalize() for n in matrix.columns],
                        matrix.columns
                    ],
                    names=(None, None, None)
                )
                matrix.to_excel(f, sheet_name=dataset)

        print(f'Saved to `{fpath}`')



def export_to_matlab(path, edge_classifications):

    G = data_manager.get_connections()['count'].copy()
    classifications = edge_classifications.copy()
    random.seed(0)

    get_matrix = lambda d: data_manager.series_to_dense_matrix(G[d]).sort_index().sort_index(axis=1)
    save_to_mat = lambda arr, name: scipy.io.savemat(os.path.join(path, f'{name}.mat'), {'arr': arr})

    l1_matrix = get_matrix('Dataset1').to_numpy().copy()
    adult_matrix = get_matrix('Dataset8').to_numpy().copy()

    l1_synapses = l1_matrix.sum()
    l1_edges = l1_matrix.astype(bool).sum()
    adult_synapses = adult_matrix.sum()
    adult_edges = adult_matrix.astype(bool).sum()


    for dataset_i, dataset in enumerate(G.columns):

        matrix = get_matrix(dataset)

        # Drop glia
        glia = [n for n in matrix.columns if ntype(n) == 'other']
        matrix = matrix.drop(glia, axis=0).drop(glia, axis=1)

        node_list = list(matrix.columns)

        # All + postemb.
        save_to_mat(matrix.to_numpy(), f'A-all-postemb_{dataset_i}')

        # All.
        postemb = [n for n in node_list if is_postemb(n)]
        matrix[postemb] = 0
        matrix.loc[postemb] = 0
        save_to_mat(matrix.to_numpy(), f'B-all_{dataset_i}')

        # Prune synapses until L1 numbers.
        matrix_pruned = matrix.to_numpy().copy()
        while matrix_pruned.astype(bool).sum() > l1_edges:
            edge_to_prune = random.choice(list(zip(*np.where(matrix_pruned > 0))))
            matrix_pruned[edge_to_prune] -= 1
        while matrix_pruned.sum() > l1_synapses:
            edge_to_prune = random.choice(list(zip(*np.where(matrix_pruned > 1))))
            matrix_pruned[edge_to_prune] -= 1
        save_to_mat(matrix_pruned, f'E-all-pruned-to-l1_{dataset_i}')

        # Randomly add synapses until adult numbers.
        matrix_grown_random = matrix.to_numpy().copy()
        all_edges = list(itertools.product(
            range(matrix_grown_random.shape[1]),
            range(matrix_grown_random.shape[0])
        ))
        while matrix_grown_random.astype(bool).sum() < adult_edges:
            edge_to_grow = random.choice(all_edges)
            matrix_grown_random[edge_to_grow] += 1
        nonzero_edges = list(zip(*np.where(matrix_grown_random > 0)))
        while matrix_grown_random.sum() < adult_synapses:
            edge_to_grow = random.choice(nonzero_edges)
            matrix_grown_random[edge_to_grow] += 1
        save_to_mat(matrix_grown_random, f'F-all-grown-to-adult-random_{dataset_i}')

        # Add synapses to existing cells until adult adult numbers.
        matrix_grown = matrix.to_numpy().copy()
        pres = range(matrix_grown.shape[1])
        posts = range(matrix_grown.shape[0])
        pre_synapses = matrix_grown.sum(axis=0)
        post_synapses = matrix_grown.sum(axis=1)
        while matrix_grown.astype(bool).sum() < adult_edges:
            pre_to_grow = random.choices(pres, weights=pre_synapses)[0]
            post_to_grow = random.choices(posts, weights=post_synapses)[0]
            matrix_grown[post_to_grow, pre_to_grow] += 1
        nonzero_edges = list(zip(*np.where(matrix_grown > 0)))
        nonzero_edge_weights = [pre_synapses[n1] + post_synapses[n2] for n1, n2 in nonzero_edges]
        while matrix_grown.sum() < adult_synapses:
            edge_to_grow = random.choices(nonzero_edges, nonzero_edge_weights)[0]
            matrix_grown[edge_to_grow] += 1
        save_to_mat(matrix_grown, f'G-all-grown-to-adult_{dataset_i}')

        # No variable.
        variable_edges = classifications[classifications.isin(['noise', 'remainder'])].index
        for pre, post in variable_edges:
            if pre not in node_list or post not in node_list:
                continue
            matrix.loc[post, pre] = 0
        save_to_mat(matrix.to_numpy(), f'C-no-variable_{dataset_i}')

        # Only stable.
        dynamic_edges = classifications[classifications.isin(['increase', 'decrease'])].index
        for pre, post in dynamic_edges:
            if pre not in node_list or post not in node_list:
                continue
            matrix.loc[post, pre] = 0
        save_to_mat(matrix.to_numpy(), f'D-only_stable_{dataset_i}')


    # Save cell list.
    pd.Series(range(1, len(node_list)+1), index=node_list).to_csv(os.path.join(path, 'node_int.csv'), header=False)

    # # Save list of left-right pairs (why?)
    # pairs = defaultdict(list)
    # for i, n in enumerate(node_list, 1):
    #     pair = npair(n)
    #     if pair == n:
    #         continue
    #     pairs[pair].append(i)
    # with open(os.path.join(path, 'node_pairs.csv'), 'w') as f:
    #     for pair in pairs.values():
    #         f.write(f'{pair[0]},{pair[1]}\n')

