import os
import subprocess
import sys
import tempfile
import warnings
from multiprocessing import Pool

import tqdm
from Bio import SeqIO
from Bio.Alphabet import IUPAC
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord

#bedtools getfasta -fo /tmp/pybedtools.423huf8a.tmp -fi /data/lfainoData/lorean/LoReAn_Example/JR2/LoReAn_annotation/run/chr8.fasta.masked.fasta.rename.fasta -bed /tmp/pybedtools.aeqgr5mv.tmp

EXONERATE = 'exonerate --model protein2genome --bestn 1  --showtargetgff TRUE --showquerygff TRUE --showalignment FALSE --showvulgar FALSE  --query %s --target %s' #--refine region
BLASTP = 'diamond blastp -q %s --db %s -k 1 -p %s'
CONVERT = 'exonerate_gff_to_alignment_gff3.pl %s'
BEDTOOLS = 'bedtools getfasta -fo %s -fi %s -bed %s'
MAKEDB = 'diamond makedb --in %s -d %s -p %s'

warnings.filterwarnings("ignore")
gencode = {
      'ATA':'I', 'ATC':'I', 'ATT':'I', 'ATG':'M',
      'ACA':'T', 'ACC':'T', 'ACG':'T', 'ACT':'T',
      'AAC':'N', 'AAT':'N', 'AAA':'K', 'AAG':'K',
      'AGC':'S', 'AGT':'S', 'AGA':'R', 'AGG':'R',
      'CTA':'L', 'CTC':'L', 'CTG':'L', 'CTT':'L',
      'CCA':'P', 'CCC':'P', 'CCG':'P', 'CCT':'P',
      'CAC':'H', 'CAT':'H', 'CAA':'Q', 'CAG':'Q',
      'CGA':'R', 'CGC':'R', 'CGG':'R', 'CGT':'R',
      'GTA':'V', 'GTC':'V', 'GTG':'V', 'GTT':'V',
      'GCA':'A', 'GCC':'A', 'GCG':'A', 'GCT':'A',
      'GAC':'D', 'GAT':'D', 'GAA':'E', 'GAG':'E',
      'GGA':'G', 'GGC':'G', 'GGG':'G', 'GGT':'G',
      'TCA':'S', 'TCC':'S', 'TCG':'S', 'TCT':'S',
      'TTC':'F', 'TTT':'F', 'TTA':'L', 'TTG':'L',
      'TAC':'Y', 'TAT':'Y', 'TAA':'Z', 'TAG':'Z',
      'TGC':'C', 'TGT':'C', 'TGA':'Z', 'TGG':'W'}

basepairs = {'A':'T', 'C':'G', 'G':'C', 'T':'A'}

def translate_frameshifted( sequence ):
      translate = ''.join([gencode.get(sequence[3*i:3*i+3],'X') for i in range(len(sequence)//3)])
      return translate

def reverse_complement( sequence ):
      reversed_sequence = (sequence[::-1])
      rc = ''.join([basepairs.get(reversed_sequence[i], 'X') for i in range(len(sequence))])
      return rc

def transeq(data):
    dummy = int(data[1])
    record = data[0]
    if dummy == 0:
        prot = (translate_frameshifted(record.seq[0:]))
        prot_rec = (SeqRecord(Seq(prot, IUPAC.protein), id=record.id + "_strand0plus"))
    if dummy == 1:
        prot = (translate_frameshifted(record.seq[1:]))  # second frame
        prot_rec = (SeqRecord(Seq(prot, IUPAC.protein), id=record.id + "_strand1plus"))
    if dummy == 2:
        prot = (translate_frameshifted(record.seq[2:]))  # third frame
        prot_rec =(SeqRecord(Seq(prot, IUPAC.protein), id=record.id + "_strand2plus"))
    if dummy == 3:
        prot = (translate_frameshifted(reverse_complement(record.seq)))  # negative first frame
        prot_rec = (SeqRecord(Seq(prot, IUPAC.protein), id=record.id + "_strand0minus"))
    if dummy == 4:
        prot = (translate_frameshifted(reverse_complement(record.seq[:len(record.seq) - 1])))  # negative second frame
        prot_rec =(SeqRecord(Seq(prot, IUPAC.protein), id=record.id + "_strand1minus"))
    if dummy == 5:
        prot = (translate_frameshifted(reverse_complement(record.seq[:len(record.seq) - 2])))  # negative third frame
        prot_rec = (SeqRecord(Seq(prot, IUPAC.protein), id=record.id + "_strand2minus"))
    return(prot_rec)


def protAlign(genome, fasta, nproc, wd, verbose):
    translate_genome = os.path.join(wd, "test.fasta")
    results_get = []
    genome_dict = SeqIO.to_dict(SeqIO.parse(genome, "fasta"))

    list_fasta = []

    for record in genome_dict:
        count = 0
        for strand in range(6):
            count += 1
            list_fasta.append([genome_dict[record], str(strand)])
    pool = Pool(processes=int(nproc))
    for x in tqdm.tqdm(pool.imap_unordered(transeq, list_fasta), total=len(list_fasta)):
        results_get.append(x)
        pass
    with open(translate_genome, "w") as output_handle:
        SeqIO.write(results_get, output_handle, "fasta")

    com = MAKEDB % (translate_genome, translate_genome, str(nproc))
    if verbose:
        sys.stdout.write(com)
    call = subprocess.Popen(com, shell=True , cwd = wd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    call.communicate()

    com = BLASTP % (fasta, translate_genome, str(nproc))
    if verbose:
        sys.stdout.write(com)
    call = subprocess.Popen(com, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out_b, err_b = call.communicate()
    list_match = out_b.decode().split("\n")
    record_dict = {}
    for record in SeqIO.parse(fasta, "fasta"):
        if record.id not in record_dict:
            record_dict[record.id] = record

    list_fasta = []
    for align in list_match:
        if align != "":
            name_prot = align.split("\t")
            list_fasta.append([align, genome, record_dict[name_prot[0]], len(genome_dict[name_prot[1].split("_")[0]].seq), wd])
    pool = Pool(processes=int(nproc))
    results_get = []
    sys.stdout.write("###RUNNING EXONERATE ###\n")
    for x in tqdm.tqdm(pool.imap_unordered(runExonerate, list_fasta), total=len(list_fasta)):
        results_get.append(x)
        pass
    with open(os.path.join(wd, "protein_evidence.gff3"), "w") as fh:
        for gene in results_get:
            if gene is not None:
                coords = gene.split("\n")
                for line in coords:
                    if line.strip() != "":
                        elem = line.split("\t")
                        location = elem[0].split(":")
                        start = location[1].split("-")[0]
                        elem[0] = location[0]
                        elem[3] = str(int(start) + int(elem[3]))
                        elem[4] = str(int(start) + int(elem[4]))
                        fh.write("\t".join(elem) + "\n")
    return


def runExonerate(sequence):
    elem = sequence[0].split("\t")
    name_prot = os.path.join(sequence[4],  elem[0] + ".fasta")
    name_gff = os.path.join(sequence[4],  elem[0] + ".gff")
    if not os._exists(name_gff):
        with open(name_prot, "w") as output_handle:
            SeqIO.write(sequence[2] , output_handle, "fasta")
        if float(elem[10]) < 1e-5:
            if elem[1].endswith("plus"):
                begin = (int(elem[8]) * 3) - 100000
                stop = (int(elem[9]) * 3)  + 100000
                if begin < 0 :
                    begin = "0"
                else:
                    begin = str(begin)
                if stop > int(elem[9] * 3):
                    stop = elem[3] * 3 - 3
                else:
                    stop = str(stop)
            else:
                stop = int(sequence[3]) - (int(elem[8]) * 3)
                begin = int(sequence[3]) -(int(elem[9]) * 3)
                begin = begin - 100000
                stop = stop  + 100000
                if begin < 0 :
                    begin = "0"
                else:
                    begin = str(begin)
                if stop > int(elem[9] * 3):
                    stop = elem[3] * 3 - 3
                else:
                    stop = str(stop)
            chr = elem[1].split("_")[0]
            new_coords = "\t".join([chr, begin, stop]) + "\n"
            outfile_bed = tempfile.NamedTemporaryFile()
            with open(outfile_bed.name, "w") as fp:
                fp.write(new_coords)
            outfile_fo_fasta = tempfile.NamedTemporaryFile()
            com_bedtools = BEDTOOLS % (outfile_fo_fasta.name, sequence[1], outfile_bed.name)
            call_bedtools= subprocess.Popen(com_bedtools, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            call_bedtools.communicate()
            com_exo = EXONERATE % (name_prot, outfile_fo_fasta.name)

            with open(name_gff, "w") as fh:
                call_exo = subprocess.Popen(com_exo, shell=True, stdout=fh, stderr=subprocess.PIPE)
            call_exo.communicate()
        com_conv = CONVERT % name_gff
        call_conv = subprocess.Popen(com_conv, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = call_conv.communicate()
        output = out.decode()
        return (output)

if __name__ == '__main__':
    protAlign(*sys.argv[1:])


#Contig1 nap-nr_minus_rice.fasta nucleotide_to_protein_match     8208    8276    50.00   +       .       ID=match.nap.nr_minus_rice.fasta.120;Target=RF|XP_623193.1|66524404|XM_623190 1 23