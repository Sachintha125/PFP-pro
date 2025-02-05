import os
import obonet
import pickle
from collections import defaultdict
import networkx as nx
import csv
import numpy as np

cif_directory_path = 'D:\\sachintha\\structures\\'
sift_file_path = 'D:\\sachintha\\data preprocess\\pdb_chain_go.csv'
string_prot_file = 'D:\\sachintha\\data preprocess\\protein.info.v12.0.txt'
obo_file = 'D:\\sachintha\\data preprocess\\go-basic.obo'
output_dir = 'D:\\sachintha\\data preprocess\\'


cif_file_list = os.listdir(cif_directory_path)
cif_file_list = [f for f in cif_file_list if os.path.isfile(os.path.join(cif_directory_path, f))]
exp_evidence_codes = set(['EXP', 'IDA', 'IPI', 'IMP', 'IGI', 'IEP', 'TAS', 'IC', 'CURATED'])
root_terms = set(['GO:0008150', 'GO:0003674', 'GO:0005575'])


def getPDBUnipMap(sift_path):
    pdb_unip_map = dict()   # no chain id obly pdb id

    with open(sift_path, 'r') as f:
        for line in f: 
            line = line.strip()
            if not line.startswith('#') and line: 
                line = line.split(',')
                if len(line) < 4:  
                    continue
                pdb_id, _, unip_id, *_ = line  

                if pdb_id not in pdb_unip_map:
                    pdb_unip_map[pdb_id] = unip_id
    return pdb_unip_map


def mapCIFIds(cif_file_list, pdb_unip_map):
    cif_id_list = [f.split('.')[0] for f in cif_file_list]
    plant_unip_mapped_dict = {cif: pdb_unip_map[cif] for cif in cif_id_list if cif in pdb_unip_map.keys()}
    return plant_unip_mapped_dict


def getStringIds(string_id_file):
    string_ids = []
    with open(string_id_file, 'r') as f:
        for line in f: 
            line = line.strip()
            if not line.startswith('#') and line: 
                line = line.split('\t')
                id = line[0].split('.')[1]
                string_ids.append(id)
    return string_ids


def getPDBStringIntersection(my_uniprot_list, string_ids):
    my_uniprot_list = set(my_uniprot_list)
    string_ids = set(string_ids)
    intersec = my_uniprot_list.intersection(string_ids)
    return intersec


def getPDBChains(plant_unip_mapped_dict, sift_file):
    from itertools import chain
    inverse_dict = defaultdict(list)
    for k, v in plant_unip_mapped_dict.items():
        inverse_dict[v].append(k)
    all_values = list(chain(*inverse_dict.values()))
    chains = []
    with open(sift_file, 'r') as f:
        for line in f:  
                line = line.strip()
                if not line.startswith('#') and line:  
                    line = line.split(',')
                    if len(line) < 4:  # Ensure line has enough columns
                        continue
                    pdb_id, chain,  *_ = line 
                    if pdb_id in all_values:
                        chains.append(pdb_id.upper()+'-'+chain)
    chains = set(chains)
    return chains


def load_go_graph(fname):
    # read *.obo file
    go_graph = obonet.read_obo(open(fname, 'r'))
    return go_graph


def read_sifts(sift_name, chains, go_graph):
    print ("### Loading SIFTS annotations...")
    pdb2go = {}
    go2info = {}
    with open(sift_name, mode='r') as tsvfile:
        reader = csv.reader(tsvfile, delimiter=',')
        next(reader, None)  # skip the headers
        next(reader, None)  # skip the headers
        for row in reader:
            pdb = row[0].strip().upper()
            chain = row[1].strip()
            evidence = row[4].strip()
            go_id = row[5].strip()
            pdb_chain = pdb + '-' + chain
            if (pdb_chain in chains) and (go_id in go_graph) and (go_id not in root_terms):
                if pdb_chain not in pdb2go:
                    pdb2go[pdb_chain] = {'goterms': [go_id], 'evidence': [evidence]}
                namespace = go_graph.nodes[go_id]['namespace']
                go_ids = nx.descendants(go_graph, go_id)
                go_ids.add(go_id)
                go_ids = go_ids.difference(root_terms)
                for go in go_ids:
                    pdb2go[pdb_chain]['goterms'].append(go)
                    pdb2go[pdb_chain]['evidence'].append(evidence)
                    name = go_graph.nodes[go]['name']
                    if go not in go2info:
                        go2info[go] = {'ont': namespace, 'goname': name, 'pdb_chains': set([pdb_chain])}
                    else:
                        go2info[go]['pdb_chains'].add(pdb_chain)
    return pdb2go, go2info


def write_prot_list(protein_list, filename):
    # write list of protein IDs
    fWrite = open(filename, 'w')
    for p in protein_list:
        fWrite.write("%s\n" % (p))
    fWrite.close()


def write_output_files(fname, pdb2go, go2info):
    # select goterms (> 49, < 5000)
    onts = ['molecular_function', 'biological_process', 'cellular_component']
    selected_goterms = {ont: set() for ont in onts}
    selected_proteins = set()
    for goterm in go2info:
        prots = go2info[goterm]['pdb_chains']
        num = len(prots)
        namespace = go2info[goterm]['ont']
        if num > 49 and num <= 5000:
            selected_goterms[namespace].add(goterm)
            selected_proteins = selected_proteins.union(prots)
    selected_goterms_list = {ont: list(selected_goterms[ont]) for ont in onts}
    selected_gonames_list = {ont: [go2info[goterm]['goname'] for goterm in selected_goterms_list[ont]] for ont in onts}

    for ont in onts:
        print ("###", ont, ":", len(selected_goterms_list[ont]))

    protein_list = []
    with open(fname + '_annot.tsv', 'wt', newline='') as out_file:
        tsv_writer = csv.writer(out_file, delimiter='\t')
        for ont in onts:
            tsv_writer.writerow(["### GO-terms (%s)" % (ont)])
            tsv_writer.writerow(selected_goterms_list[ont])
            tsv_writer.writerow(["### GO-names (%s)" % (ont)])
            tsv_writer.writerow(selected_gonames_list[ont])
        tsv_writer.writerow(["### PDB-chain", "GO-terms (molecular_function)", "GO-terms (biological_process)", "GO-terms (cellular_component)"])
        for chain in selected_proteins:
            goterms = set(pdb2go[chain]['goterms'])
            if len(goterms) > 2:
                # selected goterms
                mf_goterms = goterms.intersection(set(selected_goterms_list[onts[0]]))
                bp_goterms = goterms.intersection(set(selected_goterms_list[onts[1]]))
                cc_goterms = goterms.intersection(set(selected_goterms_list[onts[2]]))
                if len(mf_goterms) > 0 or len(bp_goterms) > 0 or len(cc_goterms) > 0:
                    protein_list.append(chain)
                    tsv_writer.writerow([chain, ','.join(mf_goterms), ','.join(bp_goterms), ','.join(cc_goterms)])

    np.random.seed(1234)
    np.random.shuffle(protein_list)
    print ("Total number of annot nrPDB=%d" % (len(protein_list)))

    # select test set based in 30% sequence identity
    test_list = set()
    i = 0
    while len(test_list) < 5000 and i < len(protein_list):
        goterms = pdb2go[protein_list[i]]['goterms']
        evidence = pdb2go[protein_list[i]]['evidence']
        goterm2evidence = {goterms[i]: evidence[i] for i in range(len(goterms))}

        # selected goterms
        mf_goterms = set(goterms).intersection(set(selected_goterms_list[onts[0]]))
        bp_goterms = set(goterms).intersection(set(selected_goterms_list[onts[1]]))
        cc_goterms = set(goterms).intersection(set(selected_goterms_list[onts[2]]))

        mf_evidence = [goterm2evidence[goterm] for goterm in mf_goterms]
        mf_evidence = [1 if evid in exp_evidence_codes else 0 for evid in mf_evidence]

        bp_evidence = [goterm2evidence[goterm] for goterm in bp_goterms]
        bp_evidence = [1 if evid in exp_evidence_codes else 0 for evid in bp_evidence]

        cc_evidence = [goterm2evidence[goterm] for goterm in cc_goterms]
        cc_evidence = [1 if evid in exp_evidence_codes else 0 for evid in cc_evidence]

        if len(mf_goterms) > 0 and len(bp_goterms) > 0 and len(cc_goterms) > 0:
            if sum(mf_evidence) > 0 and sum(bp_evidence) > 0 and sum(cc_evidence) > 0:
                test_list.add(protein_list[i])
        i += 1

    print ("Total number of test nrPDB=%d" % (len(test_list)))

    protein_list = list(set(protein_list).difference(test_list))
    np.random.shuffle(protein_list)

    idx = int(0.9*len(protein_list))
    write_prot_list(test_list, fname + '_test.txt')
    write_prot_list(protein_list[:idx], fname + '_train.txt')
    write_prot_list(protein_list[idx:], fname + '_valid.txt')


pdb_unip_map = getPDBUnipMap(sift_file_path)
plant_unip_mapped_dict = mapCIFIds(cif_file_list, pdb_unip_map)
all_string_prots = getStringIds(string_prot_file)
plant_struct_with_ppi = getPDBStringIntersection(list(plant_unip_mapped_dict.values()), all_string_prots)
pdb_chains = getPDBChains(plant_unip_mapped_dict, sift_file_path)
go_graph = load_go_graph(obo_file)
pdb2go, go2info = read_sifts(sift_file_path, pdb_chains, go_graph)
write_output_files(output_dir, pdb2go, go2info)

with open(f'{output_dir}plant_unip_mapped_dict.pkl', 'wb') as f:
    pickle.dump(plant_unip_mapped_dict, f)

with open(f'{output_dir}plant_struct_with_ppi_unip_id_list.pkl', 'wb') as f:
    pickle.dump(plant_struct_with_ppi, f)
