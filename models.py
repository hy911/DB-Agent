# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
import re
from typing import List

from django.db import models
from django.db.models import QuerySet, F, Q

from utils.constant import MODEL_TYPE
from utils.db_models import RuleModel


def get_numbers(dct) -> list:
    """
    提取字符串中的数字
    Args:
        dct:

    Returns:

    """
    text = dct["passage"]
    numbers = re.findall(r"\d+", text)
    return numbers


class CancerTypeShortNames(models.Model):
    id = models.BigAutoField(primary_key=True)
    cancer_type = models.CharField(max_length=255, blank=True, null=True)
    cancer_type_short_name = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "cancer_type_short_names"


class CclDescInfo(models.Model):
    id = models.BigAutoField(primary_key=True)
    species = models.TextField(blank=True, null=True)
    cancer_cell_line_id = models.CharField(max_length=255, blank=True, null=True)
    cell_line_name = models.CharField(max_length=255, blank=True, null=True)
    stripped_cell_line_name = models.CharField(max_length=255, blank=True, null=True)
    ccle_name = models.CharField(
        db_column="CCLE_Name", max_length=255, blank=True, null=True
    )  # Field name made lowercase.
    alias = models.CharField(max_length=255, blank=True, null=True)
    cosmicid = models.IntegerField(
        db_column="COSMICID", blank=True, null=True
    )  # Field name made lowercase.
    sex = models.CharField(max_length=255, blank=True, null=True)
    source = models.TextField(blank=True, null=True)
    achilles_n_replicates = models.IntegerField(
        db_column="Achilles_n_replicates", blank=True, null=True
    )  # Field name made lowercase.
    cell_line_nnmd = models.DecimalField(
        db_column="cell_line_NNMD",
        max_digits=20,
        decimal_places=8,
        blank=True,
        null=True,
    )  # Field name made lowercase.
    culture_type = models.CharField(max_length=255, blank=True, null=True)
    culture_medium = models.TextField(blank=True, null=True)
    cas9_activity = models.DecimalField(
        max_digits=18, decimal_places=6, blank=True, null=True
    )
    rrid = models.CharField(
        db_column="RRID", max_length=255, blank=True, null=True
    )  # Field name made lowercase.
    wtsi_master_cell_id = models.IntegerField(
        db_column="WTSI_Master_Cell_ID", blank=True, null=True
    )  # Field name made lowercase.
    sample_collection_site = models.CharField(max_length=255, blank=True, null=True)
    primary_or_metastasis = models.CharField(max_length=255, blank=True, null=True)
    primary_disease = models.CharField(max_length=255, blank=True, null=True)
    subtype = models.TextField(
        db_column="Subtype", blank=True, null=True
    )  # Field name made lowercase.
    age = models.IntegerField(blank=True, null=True)
    sanger_model_id = models.CharField(
        db_column="Sanger_Model_ID", max_length=255, blank=True, null=True
    )  # Field name made lowercase.
    depmap_public_comments = models.TextField(blank=True, null=True)
    lineage = models.CharField(max_length=255, blank=True, null=True)
    lineage_subtype = models.CharField(max_length=255, blank=True, null=True)
    lineage_sub_subtype = models.CharField(max_length=255, blank=True, null=True)
    lineage_molecular_subtype = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "ccl_desc_info"


class CclExpressionData(models.Model):
    id = models.BigAutoField(primary_key=True)
    cancer_cell_line_id = models.CharField(max_length=255, blank=True, null=True)
    gene_symbol = models.CharField(max_length=255, blank=True, null=True)
    log2tpm = models.DecimalField(
        max_digits=18, decimal_places=6, blank=True, null=True
    )
    species = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "ccl_expression_data"


class CclFusionData(models.Model):
    id = models.BigAutoField(primary_key=True)
    cancer_cell_line_id = models.CharField(max_length=255, blank=True, null=True)
    species = models.TextField(blank=True, null=True)
    fusionname = models.CharField(
        db_column="FusionName", max_length=255, blank=True, null=True
    )  # Field name made lowercase.
    junctionreadcount = models.IntegerField(
        db_column="JunctionReadCount", blank=True, null=True
    )  # Field name made lowercase.
    spanningfragcount = models.IntegerField(
        db_column="SpanningFragCount", blank=True, null=True
    )  # Field name made lowercase.
    splicetype = models.CharField(
        db_column="SpliceType", max_length=255, blank=True, null=True
    )  # Field name made lowercase.
    gene_symbol = models.CharField(max_length=255, blank=True, null=True)
    gene_direction = models.CharField(max_length=255, blank=True, null=True)
    leftbreakpoint = models.CharField(
        db_column="LeftBreakpoint", max_length=255, blank=True, null=True
    )  # Field name made lowercase.
    rightbreakpoint = models.CharField(
        db_column="RightBreakpoint", max_length=255, blank=True, null=True
    )  # Field name made lowercase.
    largeanchorsupport = models.CharField(
        db_column="LargeAnchorSupport", max_length=255, blank=True, null=True
    )  # Field name made lowercase.
    ffpm = models.DecimalField(
        db_column="FFPM", max_digits=18, decimal_places=6, blank=True, null=True
    )  # Field name made lowercase.
    leftbreakdinuc = models.CharField(
        db_column="LeftBreakDinuc", max_length=255, blank=True, null=True
    )  # Field name made lowercase.
    leftbreakentropy = models.DecimalField(
        db_column="LeftBreakEntropy",
        max_digits=18,
        decimal_places=6,
        blank=True,
        null=True,
    )  # Field name made lowercase.
    rightbreakdinuc = models.CharField(
        db_column="RightBreakDinuc", max_length=255, blank=True, null=True
    )  # Field name made lowercase.
    rightbreakentropy = models.DecimalField(
        db_column="RightBreakEntropy",
        max_digits=18,
        decimal_places=6,
        blank=True,
        null=True,
    )  # Field name made lowercase.
    annots = models.TextField(blank=True, null=True)
    ccle_count = models.IntegerField(
        db_column="CCLE_count", blank=True, null=True
    )  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = "ccl_fusion_data"


class CclMutationData(models.Model):
    id = models.BigAutoField(primary_key=True)
    gene_symbol = models.CharField(max_length=255, blank=True, null=True)
    entrez_gene_id = models.IntegerField(
        db_column="Entrez_Gene_Id", blank=True, null=True
    )  # Field name made lowercase.
    ncbi_build = models.IntegerField(
        db_column="NCBI_Build", blank=True, null=True
    )  # Field name made lowercase.
    chromosome = models.IntegerField(
        db_column="Chromosome", blank=True, null=True
    )  # Field name made lowercase.
    start_position = models.IntegerField(
        db_column="Start_position", blank=True, null=True
    )  # Field name made lowercase.
    end_position = models.IntegerField(
        db_column="End_position", blank=True, null=True
    )  # Field name made lowercase.
    strand = models.CharField(
        db_column="Strand", max_length=255, blank=True, null=True
    )  # Field name made lowercase.
    variant_classification = models.CharField(
        db_column="Variant_Classification", max_length=255, blank=True, null=True
    )  # Field name made lowercase.
    variant_type = models.CharField(
        db_column="Variant_Type", max_length=255, blank=True, null=True
    )  # Field name made lowercase.
    reference_allele = models.TextField(
        db_column="Reference_Allele", blank=True, null=True
    )  # Field name made lowercase.
    tumor_seq_allele1 = models.TextField(
        db_column="Tumor_Seq_Allele1", blank=True, null=True
    )  # Field name made lowercase.
    dbsnp_rs = models.TextField(
        db_column="dbSNP_RS", blank=True, null=True
    )  # Field name made lowercase.
    dbsnp_val_status = models.CharField(
        db_column="dbSNP_Val_Status", max_length=255, blank=True, null=True
    )  # Field name made lowercase.
    genome_change = models.TextField(
        db_column="Genome_Change", blank=True, null=True
    )  # Field name made lowercase.
    annotation_transcript = models.CharField(
        db_column="Annotation_Transcript", max_length=255, blank=True, null=True
    )  # Field name made lowercase.
    cancer_cell_line_id = models.CharField(max_length=255, blank=True, null=True)
    cdna_change = models.TextField(
        db_column="cDNA_Change", blank=True, null=True
    )  # Field name made lowercase.
    codon_change = models.TextField(
        db_column="Codon_Change", blank=True, null=True
    )  # Field name made lowercase.
    protein_change = models.TextField(
        db_column="Protein_Change", blank=True, null=True
    )  # Field name made lowercase.
    isdeleterious = models.BooleanField(
        db_column="isDeleterious", blank=True, null=True
    )  # Field name made lowercase.
    istcgahotspot = models.BooleanField(
        db_column="isTCGAhotspot", blank=True, null=True
    )  # Field name made lowercase.
    tcgahscnt = models.IntegerField(
        db_column="TCGAhsCnt", blank=True, null=True
    )  # Field name made lowercase.
    iscosmichotspot = models.BooleanField(
        db_column="isCOSMIChotspot", blank=True, null=True
    )  # Field name made lowercase.
    cosmichscnt = models.IntegerField(
        db_column="COSMIChsCnt", blank=True, null=True
    )  # Field name made lowercase.
    exac_af = models.DecimalField(
        db_column="ExAC_AF", max_digits=20, decimal_places=8, blank=True, null=True
    )  # Field name made lowercase.
    variant_annotation = models.CharField(
        db_column="Variant_annotation", max_length=255, blank=True, null=True
    )  # Field name made lowercase.
    cga_wes_ac = models.CharField(
        db_column="CGA_WES_AC", max_length=255, blank=True, null=True
    )  # Field name made lowercase.
    hc_ac = models.CharField(
        db_column="HC_AC", max_length=255, blank=True, null=True
    )  # Field name made lowercase.
    rd_ac = models.CharField(
        db_column="RD_AC", max_length=255, blank=True, null=True
    )  # Field name made lowercase.
    rnaseq_ac = models.CharField(
        db_column="RNAseq_AC", max_length=255, blank=True, null=True
    )  # Field name made lowercase.
    sangerwes_ac = models.CharField(
        db_column="SangerWES_AC", max_length=255, blank=True, null=True
    )  # Field name made lowercase.
    wgs_ac = models.CharField(
        db_column="WGS_AC", max_length=255, blank=True, null=True
    )  # Field name made lowercase.
    species = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "ccl_mutation_data"


class GeneInfo(models.Model):
    id = models.BigAutoField(primary_key=True)
    species = models.TextField(blank=True, null=True)
    tax_id = models.IntegerField(blank=True, null=True)
    geneid = models.IntegerField(
        db_column="GeneID", blank=True, null=True
    )  # Field name made lowercase.
    symbol = models.TextField(
        db_column="Symbol", blank=True, null=True, unique=True
    )  # Field name made lowercase.
    locustag = models.TextField(
        db_column="LocusTag", blank=True, null=True
    )  # Field name made lowercase.
    synonyms = models.TextField(
        db_column="Synonyms", blank=True, null=True
    )  # Field name made lowercase.
    dbxrefs = models.TextField(
        db_column="dbXrefs", blank=True, null=True
    )  # Field name made lowercase.
    chromosome = models.IntegerField(blank=True, null=True)
    map_location = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    type_of_gene = models.TextField(blank=True, null=True)
    symbol_from_nomenclature_authority = models.TextField(
        db_column="Symbol_from_nomenclature_authority", blank=True, null=True
    )  # Field name made lowercase.
    full_name_from_nomenclature_authority = models.TextField(
        db_column="Full_name_from_nomenclature_authority", blank=True, null=True
    )  # Field name made lowercase.
    nomenclature_status = models.IntegerField(
        db_column="Nomenclature_status", blank=True, null=True
    )  # Field name made lowercase.
    other_designations = models.TextField(
        db_column="Other_designations", blank=True, null=True
    )  # Field name made lowercase.
    modification_date = models.DateField(
        db_column="Modification_date", blank=True, null=True
    )  # Field name made lowercase.
    feature_type = models.TextField(
        db_column="Feature_type", blank=True, null=True
    )  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = "gene_info"


class GeneInfoCopy1(models.Model):
    id = models.BigAutoField(primary_key=True)
    species = models.TextField(blank=True, null=True)
    tax_id = models.IntegerField(blank=True, null=True)
    geneid = models.IntegerField(
        db_column="GeneID", blank=True, null=True
    )  # Field name made lowercase.
    symbol = models.TextField(
        db_column="Symbol", blank=True, null=True
    )  # Field name made lowercase.
    locustag = models.TextField(
        db_column="LocusTag", blank=True, null=True
    )  # Field name made lowercase.
    synonyms = models.TextField(
        db_column="Synonyms", blank=True, null=True
    )  # Field name made lowercase.
    dbxrefs = models.TextField(
        db_column="dbXrefs", blank=True, null=True
    )  # Field name made lowercase.
    chromosome = models.IntegerField(blank=True, null=True)
    map_location = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    type_of_gene = models.TextField(blank=True, null=True)
    symbol_from_nomenclature_authority = models.TextField(
        db_column="Symbol_from_nomenclature_authority", blank=True, null=True
    )  # Field name made lowercase.
    full_name_from_nomenclature_authority = models.TextField(
        db_column="Full_name_from_nomenclature_authority", blank=True, null=True
    )  # Field name made lowercase.
    nomenclature_status = models.IntegerField(
        db_column="Nomenclature_status", blank=True, null=True
    )  # Field name made lowercase.
    other_designations = models.TextField(
        db_column="Other_designations", blank=True, null=True
    )  # Field name made lowercase.
    modification_date = models.DateField(
        db_column="Modification_date", blank=True, null=True
    )  # Field name made lowercase.
    feature_type = models.TextField(
        db_column="Feature_type", blank=True, null=True
    )  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = "gene_info_copy1"


class GeneSet(models.Model):
    id = models.BigAutoField(primary_key=True)
    gene_symbol = models.CharField(max_length=255, blank=True, null=True)
    species = models.TextField(blank=True, null=True)
    gene_set = models.CharField(max_length=255, blank=True, null=True)
    gene_subset = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "gene_set"


class GeneSynonyms(models.Model):
    id = models.BigAutoField(primary_key=True)
    gene_symbol = models.ForeignKey(
        "GeneInfo",
        to_field="symbol",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="gene_symbol",
    )
    species = models.TextField(blank=True, null=True)
    synonym = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "gene_synonyms"


class ImmuneCellSynonyms(models.Model):
    id = models.BigAutoField(primary_key=True)
    immune_cell_id = models.CharField(
        max_length=255, blank=True, null=True, unique=True
    )
    immune_cell_name = models.CharField(max_length=255, blank=True, null=True)
    immune_cell_dataset_field = models.CharField(
        db_column="immune_cell_dataset\r", max_length=255, blank=True, null=True
    )  # Field renamed to remove unsuitable characters. Field renamed because it ended with '_'.
    immune_cell_synonym_field = models.CharField(
        db_column="immune_cell_synonym\r", max_length=255, blank=True, null=True
    )  # Field renamed to remove unsuitable characters. Field renamed because it ended with '_'.

    class Meta:
        managed = False
        db_table = "immune_cell_synonyms"


class ImmuneSignatureSynonyms(models.Model):
    id = models.BigAutoField(primary_key=True)
    immune_signature_id = models.CharField(
        max_length=255, blank=True, null=True, unique=True
    )
    immune_signature_name = models.CharField(max_length=255, blank=True, null=True)
    immune_subtype_algorithm = models.CharField(max_length=255, blank=True, null=True)
    immune_signature_synonym = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "immune_signature_synonyms"


class ModelCclMapping(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_uuid = models.CharField(max_length=255, blank=True, null=True)
    model_id = models.CharField(max_length=255, blank=True, null=True)
    species = models.TextField(blank=True, null=True)
    ccl_name = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "model_ccl_mapping"


class ModelDescInfo(models.Model):
    id = models.CharField(max_length=255, blank=True, null=True)
    model_id = models.CharField(max_length=255, blank=True, null=True, unique=True)
    model_type = models.CharField(max_length=255, blank=True, null=True)
    model_name = models.CharField(max_length=255, blank=True, null=True)
    cancer_type = models.CharField(max_length=255, blank=True, null=True)
    msi_status = models.CharField(max_length=255, blank=True, null=True)
    cancer_subtype_short_names = models.CharField(max_length=255, blank=True, null=True)
    model_name_outer = models.CharField(max_length=255, blank=True, null=True)
    rnaseq_id = models.CharField(max_length=255, blank=True, null=True)
    model_uuid = models.CharField(
        primary_key=True, max_length=255, unique=True, db_index=True
    )
    second_model_type = models.CharField(max_length=255, blank=True, null=True)
    ccle_line = models.CharField(max_length=150, blank=True, null=True)
    ccle_stripped_cell_line_name = models.CharField(
        max_length=150, blank=True, null=True
    )
    ccle_id = models.TextField(blank=True, null=True)
    transcription_level_mutation_count = models.BigIntegerField(blank=True, null=True)
    is_cancer_model = models.CharField(max_length=32, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "model_desc_info"

    def get_mapping_model_type(self):
        for k, v in MODEL_TYPE.items():
            if self.model_type in v:
                return k

    @classmethod
    def check_model_type(cls, model_id, model_type) -> bool:
        obj = cls.objects.get(model_id=model_id)
        model_type = model_type.upper()
        for i in [
            obj.model_type.strip().upper(),
            obj.second_model_type.strip().upper(),
        ]:
            if i.startswith(model_type):
                return True
        return False


class ExpressionData(models.Model):
    rnaseq_id = models.CharField(max_length=255, blank=True, null=True)
    species = models.TextField(blank=True, null=True)
    gene_symbol = models.CharField(max_length=255, blank=True, null=True)
    tpm = models.DecimalField(max_digits=18, decimal_places=6, blank=True, null=True)
    count = models.DecimalField(max_digits=18, decimal_places=6, blank=True, null=True)
    fpkm = models.DecimalField(max_digits=18, decimal_places=6, blank=True, null=True)
    log2tpm = models.DecimalField(
        max_digits=18, decimal_places=6, blank=True, null=True
    )
    model_id = models.CharField(max_length=255, blank=True, null=True)
    model_uuid = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "model_expression_data"


class ModelExpressionData(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    species = models.TextField(blank=True, null=True)
    data_source = models.TextField(blank=True, null=True)
    gene_symbol = models.ForeignKey(
        "GeneInfo",
        to_field="symbol",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="gene_symbol",
    )
    log2tpm = models.DecimalField(
        max_digits=18, decimal_places=6, blank=True, null=True
    )

    class Meta:
        managed = False
        db_table = "model_ccle_expression_data"


class FusionData(models.Model):
    rnaseq_id = models.CharField(max_length=255, blank=True, null=True)
    species = models.TextField(blank=True, null=True)
    fusionname = models.CharField(
        db_column="FusionName", max_length=255, blank=True, null=True
    )  # Field name made lowercase.
    junctionreadcount = models.IntegerField(
        db_column="JunctionReadCount", blank=True, null=True
    )  # Field name made lowercase.
    spanningfragcount = models.IntegerField(
        db_column="SpanningFragCount", blank=True, null=True
    )  # Field name made lowercase.
    splicetype = models.CharField(
        db_column="SpliceType", max_length=255, blank=True, null=True
    )  # Field name made lowercase.
    gene_symbol = models.CharField(max_length=255, blank=True, null=True)
    leftbreakpoint = models.CharField(
        db_column="LeftBreakpoint", max_length=255, blank=True, null=True
    )  # Field name made lowercase.
    gene_direction = models.CharField(max_length=255, blank=True, null=True)
    rightbreakpoint = models.CharField(
        db_column="RightBreakpoint", max_length=255, blank=True, null=True
    )  # Field name made lowercase.
    largeanchorsupport = models.CharField(
        db_column="LargeAnchorSupport", max_length=255, blank=True, null=True
    )  # Field name made lowercase.
    ffpm = models.DecimalField(
        db_column="FFPM", max_digits=18, decimal_places=6, blank=True, null=True
    )  # Field name made lowercase.
    leftbreakdinuc = models.CharField(
        db_column="LeftBreakDinuc", max_length=255, blank=True, null=True
    )  # Field name made lowercase.
    leftbreakentropy = models.DecimalField(
        db_column="LeftBreakEntropy",
        max_digits=18,
        decimal_places=6,
        blank=True,
        null=True,
    )  # Field name made lowercase.
    rightbreakdinuc = models.CharField(
        db_column="RightBreakDinuc", max_length=255, blank=True, null=True
    )  # Field name made lowercase.
    rightbreakentropy = models.DecimalField(
        db_column="RightBreakEntropy",
        max_digits=18,
        decimal_places=6,
        blank=True,
        null=True,
    )  # Field name made lowercase.
    annots = models.CharField(max_length=255, blank=True, null=True)
    model_id = models.CharField(max_length=255, blank=True, null=True)
    model_uuid = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "model_fusion_data"


class ModelFusionData(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    species = models.TextField(blank=True, null=True)
    fusionname = models.CharField(
        db_column="fusionname", max_length=255, blank=True, null=True
    )  # Field name made lowercase.
    gene_symbol = models.CharField(max_length=255, blank=True, null=True)
    gene_direction = models.CharField(max_length=255, blank=True, null=True)
    data_source = models.CharField(max_length=255, blank=True, null=True)
    ffpm = models.DecimalField(
        db_column="ffpm", max_digits=18, decimal_places=6, blank=True, null=True
    )  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = "model_ccle_fusion_data"


class ModelImmuneSubtype(models.Model):
    id = models.AutoField(primary_key=True)
    rnaseq_id = models.CharField(max_length=255, blank=True, null=True)
    immune_subtype_algorithm = models.CharField(max_length=255, blank=True, null=True)
    immune_subtype = models.CharField(max_length=255, blank=True, null=True)
    predicted_prob = models.CharField(max_length=255, blank=True, null=True)
    immune_signature_id = models.CharField(max_length=255, blank=True, null=True)
    immune_signature_value = models.DecimalField(
        max_digits=31, decimal_places=9, blank=True, null=True
    )
    species = models.CharField(max_length=255, blank=True, null=True)
    model_id = models.CharField(max_length=255, blank=True, null=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )

    class Meta:
        managed = False
        db_table = "model_immune_subtype"


class ModelImmuneTil(models.Model):
    id = models.AutoField(primary_key=True)
    rnaseq_id = models.CharField(max_length=255, blank=True, null=True)
    species = models.CharField(max_length=255, blank=True, null=True)
    immune_cell_dataset = models.CharField(max_length=255, blank=True, null=True)
    immune_cell_id = models.ForeignKey(
        "ImmuneCellSynonyms",
        to_field="immune_cell_id",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="immune_cell_id",
    )
    immune_cell_value = models.DecimalField(
        max_digits=31, decimal_places=9, blank=True, null=True
    )
    # model_id = models.CharField(max_length=255, blank=True, null=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )

    class Meta:
        managed = False
        db_table = "model_immune_til"


class MutationData(models.Model):
    rnaseq_id = models.CharField(max_length=255, blank=True, null=True)
    species = models.TextField(blank=True, null=True)
    gene_symbol = models.CharField(max_length=255, blank=True, null=True)
    chromosome = models.TextField(
        db_column="Chromosome", blank=True, null=True
    )  # Field name made lowercase.
    start_position = models.IntegerField(
        db_column="Start_Position", blank=True, null=True
    )  # Field name made lowercase.
    end_position = models.IntegerField(
        db_column="End_Position", blank=True, null=True
    )  # Field name made lowercase.
    strand = models.TextField(
        db_column="Strand", blank=True, null=True
    )  # Field name made lowercase.
    variant_classification = models.TextField(
        db_column="Variant_Classification", blank=True, null=True
    )  # Field name made lowercase.
    variant_type = models.TextField(
        db_column="Variant_Type", blank=True, null=True
    )  # Field name made lowercase.
    reference_allele = models.TextField(
        db_column="Reference_Allele", blank=True, null=True
    )  # Field name made lowercase.
    tumor_seq_allele1 = models.TextField(
        db_column="Tumor_Seq_Allele1", blank=True, null=True
    )  # Field name made lowercase.
    tumor_seq_allele2 = models.TextField(
        db_column="Tumor_Seq_Allele2", blank=True, null=True
    )  # Field name made lowercase.
    dbsnp_rs = models.TextField(
        db_column="dbSNP_RS", blank=True, null=True
    )  # Field name made lowercase.
    dbsnp_val_status = models.TextField(
        db_column="dbSNP_Val_Status", blank=True, null=True
    )  # Field name made lowercase.
    tumor_sample_barcode = models.TextField(
        db_column="Tumor_Sample_Barcode", blank=True, null=True
    )  # Field name made lowercase.
    matched_norm_sample_barcode = models.TextField(
        db_column="Matched_Norm_Sample_Barcode", blank=True, null=True
    )  # Field name made lowercase.
    match_norm_seq_allele1 = models.TextField(
        db_column="Match_Norm_Seq_Allele1", blank=True, null=True
    )  # Field name made lowercase.
    match_norm_seq_allele2 = models.TextField(
        db_column="Match_Norm_Seq_Allele2", blank=True, null=True
    )  # Field name made lowercase.
    tumor_validation_allele1 = models.TextField(
        db_column="Tumor_Validation_Allele1", blank=True, null=True
    )  # Field name made lowercase.
    tumor_validation_allele2 = models.TextField(
        db_column="Tumor_Validation_Allele2", blank=True, null=True
    )  # Field name made lowercase.
    match_norm_validation_allele1 = models.TextField(
        db_column="Match_Norm_Validation_Allele1", blank=True, null=True
    )  # Field name made lowercase.
    match_norm_validation_allele2 = models.TextField(
        db_column="Match_Norm_Validation_Allele2", blank=True, null=True
    )  # Field name made lowercase.
    verification_status = models.TextField(
        db_column="Verification_Status", blank=True, null=True
    )  # Field name made lowercase.
    validation_status = models.TextField(
        db_column="Validation_Status", blank=True, null=True
    )  # Field name made lowercase.
    mutation_status = models.TextField(
        db_column="Mutation_Status", blank=True, null=True
    )  # Field name made lowercase.
    sequencing_phase = models.TextField(
        db_column="Sequencing_Phase", blank=True, null=True
    )  # Field name made lowercase.
    sequence_source = models.TextField(
        db_column="Sequence_Source", blank=True, null=True
    )  # Field name made lowercase.
    validation_method = models.TextField(
        db_column="Validation_Method", blank=True, null=True
    )  # Field name made lowercase.
    score = models.TextField(
        db_column="Score", blank=True, null=True
    )  # Field name made lowercase.
    bam_file = models.TextField(
        db_column="BAM_File", blank=True, null=True
    )  # Field name made lowercase.
    sequencer = models.TextField(
        db_column="Sequencer", blank=True, null=True
    )  # Field name made lowercase.
    tumor_sample_uuid = models.TextField(
        db_column="Tumor_Sample_UUID", blank=True, null=True
    )  # Field name made lowercase.
    matched_norm_sample_uuid = models.TextField(
        db_column="Matched_Norm_Sample_UUID", blank=True, null=True
    )  # Field name made lowercase.
    hgvsc = models.TextField(
        db_column="HGVSc", blank=True, null=True
    )  # Field name made lowercase.
    hgvsp = models.TextField(
        db_column="HGVSp", blank=True, null=True
    )  # Field name made lowercase.
    hgvsp_short = models.TextField(
        db_column="HGVSp_Short", blank=True, null=True
    )  # Field name made lowercase.
    transcript_id = models.TextField(
        db_column="Transcript_ID", blank=True, null=True
    )  # Field name made lowercase.
    exon_number = models.TextField(
        db_column="Exon_Number", blank=True, null=True
    )  # Field name made lowercase.
    t_depth = models.TextField(blank=True, null=True)
    t_ref_count = models.TextField(blank=True, null=True)
    t_alt_count = models.TextField(blank=True, null=True)
    n_depth = models.TextField(blank=True, null=True)
    n_ref_count = models.TextField(blank=True, null=True)
    n_alt_count = models.TextField(blank=True, null=True)
    all_effects = models.TextField(blank=True, null=True)
    allele = models.TextField(
        db_column="Allele", blank=True, null=True
    )  # Field name made lowercase.
    gene = models.TextField(
        db_column="Gene", blank=True, null=True
    )  # Field name made lowercase.
    feature = models.TextField(
        db_column="Feature", blank=True, null=True
    )  # Field name made lowercase.
    feature_type = models.TextField(
        db_column="Feature_type", blank=True, null=True
    )  # Field name made lowercase.
    consequence = models.TextField(
        db_column="Consequence", blank=True, null=True
    )  # Field name made lowercase.
    cdna_position = models.TextField(
        db_column="cDNA_position", blank=True, null=True
    )  # Field name made lowercase.
    cds_position = models.TextField(
        db_column="CDS_position", blank=True, null=True
    )  # Field name made lowercase.
    protein_position = models.TextField(
        db_column="Protein_position", blank=True, null=True
    )  # Field name made lowercase.
    amino_acids = models.TextField(
        db_column="Amino_acids", blank=True, null=True
    )  # Field name made lowercase.
    codons = models.TextField(
        db_column="Codons", blank=True, null=True
    )  # Field name made lowercase.
    existing_variation = models.TextField(
        db_column="Existing_variation", blank=True, null=True
    )  # Field name made lowercase.
    allele_num = models.IntegerField(
        db_column="ALLELE_NUM", blank=True, null=True
    )  # Field name made lowercase.
    distance = models.TextField(
        db_column="DISTANCE", blank=True, null=True
    )  # Field name made lowercase.
    strand_vep = models.IntegerField(
        db_column="STRAND_VEP", blank=True, null=True
    )  # Field name made lowercase.
    symbol = models.TextField(
        db_column="SYMBOL", blank=True, null=True
    )  # Field name made lowercase.
    symbol_source = models.TextField(
        db_column="SYMBOL_SOURCE", blank=True, null=True
    )  # Field name made lowercase.
    hgnc_id = models.TextField(
        db_column="HGNC_ID", blank=True, null=True
    )  # Field name made lowercase.
    biotype = models.TextField(
        db_column="BIOTYPE", blank=True, null=True
    )  # Field name made lowercase.
    canonical = models.TextField(
        db_column="CANONICAL", blank=True, null=True
    )  # Field name made lowercase.
    ccds = models.TextField(
        db_column="CCDS", blank=True, null=True
    )  # Field name made lowercase.
    ensp = models.TextField(
        db_column="ENSP", blank=True, null=True
    )  # Field name made lowercase.
    swissprot = models.TextField(
        db_column="SWISSPROT", blank=True, null=True
    )  # Field name made lowercase.
    trembl = models.TextField(
        db_column="TREMBL", blank=True, null=True
    )  # Field name made lowercase.
    uniparc = models.TextField(
        db_column="UNIPARC", blank=True, null=True
    )  # Field name made lowercase.
    refseq = models.TextField(
        db_column="RefSeq", blank=True, null=True
    )  # Field name made lowercase.
    sift = models.TextField(
        db_column="SIFT", blank=True, null=True
    )  # Field name made lowercase.
    polyphen = models.TextField(
        db_column="PolyPhen", blank=True, null=True
    )  # Field name made lowercase.
    exon = models.TextField(
        db_column="EXON", blank=True, null=True
    )  # Field name made lowercase.
    intron = models.TextField(
        db_column="INTRON", blank=True, null=True
    )  # Field name made lowercase.
    domains = models.TextField(
        db_column="DOMAINS", blank=True, null=True
    )  # Field name made lowercase.
    af = models.TextField(
        db_column="AF", blank=True, null=True
    )  # Field name made lowercase.
    afr_af = models.TextField(
        db_column="AFR_AF", blank=True, null=True
    )  # Field name made lowercase.
    amr_af = models.TextField(
        db_column="AMR_AF", blank=True, null=True
    )  # Field name made lowercase.
    asn_af = models.TextField(
        db_column="ASN_AF", blank=True, null=True
    )  # Field name made lowercase.
    eas_af = models.TextField(
        db_column="EAS_AF", blank=True, null=True
    )  # Field name made lowercase.
    eur_af = models.TextField(
        db_column="EUR_AF", blank=True, null=True
    )  # Field name made lowercase.
    sas_af = models.TextField(
        db_column="SAS_AF", blank=True, null=True
    )  # Field name made lowercase.
    aa_af = models.TextField(
        db_column="AA_AF", blank=True, null=True
    )  # Field name made lowercase.
    ea_af = models.TextField(
        db_column="EA_AF", blank=True, null=True
    )  # Field name made lowercase.
    clin_sig = models.TextField(
        db_column="CLIN_SIG", blank=True, null=True
    )  # Field name made lowercase.
    somatic = models.TextField(
        db_column="SOMATIC", blank=True, null=True
    )  # Field name made lowercase.
    pubmed = models.TextField(
        db_column="PUBMED", blank=True, null=True
    )  # Field name made lowercase.
    motif_name = models.TextField(
        db_column="MOTIF_NAME", blank=True, null=True
    )  # Field name made lowercase.
    motif_pos = models.TextField(
        db_column="MOTIF_POS", blank=True, null=True
    )  # Field name made lowercase.
    high_inf_pos = models.TextField(
        db_column="HIGH_INF_POS", blank=True, null=True
    )  # Field name made lowercase.
    motif_score_change = models.TextField(
        db_column="MOTIF_SCORE_CHANGE", blank=True, null=True
    )  # Field name made lowercase.
    impact = models.TextField(
        db_column="IMPACT", blank=True, null=True
    )  # Field name made lowercase.
    pick = models.TextField(
        db_column="PICK", blank=True, null=True
    )  # Field name made lowercase.
    variant_class = models.TextField(
        db_column="VARIANT_CLASS", blank=True, null=True
    )  # Field name made lowercase.
    tsl = models.IntegerField(
        db_column="TSL", blank=True, null=True
    )  # Field name made lowercase.
    hgvs_offset = models.TextField(
        db_column="HGVS_OFFSET", blank=True, null=True
    )  # Field name made lowercase.
    pheno = models.TextField(
        db_column="PHENO", blank=True, null=True
    )  # Field name made lowercase.
    minimised = models.TextField(
        db_column="MINIMISED", blank=True, null=True
    )  # Field name made lowercase.
    gene_pheno = models.TextField(
        db_column="GENE_PHENO", blank=True, null=True
    )  # Field name made lowercase.
    filter = models.TextField(
        db_column="FILTER", blank=True, null=True
    )  # Field name made lowercase.
    flanking_bps = models.TextField(blank=True, null=True)
    vcf_id = models.TextField(blank=True, null=True)
    vcf_qual = models.DecimalField(
        max_digits=18, decimal_places=6, blank=True, null=True
    )
    gnomad_af = models.TextField(
        db_column="gnomAD_AF", blank=True, null=True
    )  # Field name made lowercase.
    gnomad_afr_af = models.TextField(
        db_column="gnomAD_AFR_AF", blank=True, null=True
    )  # Field name made lowercase.
    gnomad_amr_af = models.TextField(
        db_column="gnomAD_AMR_AF", blank=True, null=True
    )  # Field name made lowercase.
    gnomad_asj_af = models.TextField(
        db_column="gnomAD_ASJ_AF", blank=True, null=True
    )  # Field name made lowercase.
    gnomad_eas_af = models.TextField(
        db_column="gnomAD_EAS_AF", blank=True, null=True
    )  # Field name made lowercase.
    gnomad_fin_af = models.TextField(
        db_column="gnomAD_FIN_AF", blank=True, null=True
    )  # Field name made lowercase.
    gnomad_nfe_af = models.TextField(
        db_column="gnomAD_NFE_AF", blank=True, null=True
    )  # Field name made lowercase.
    gnomad_oth_af = models.TextField(
        db_column="gnomAD_OTH_AF", blank=True, null=True
    )  # Field name made lowercase.
    gnomad_sas_af = models.TextField(
        db_column="gnomAD_SAS_AF", blank=True, null=True
    )  # Field name made lowercase.
    vcf_pos = models.IntegerField(blank=True, null=True)
    id = models.BigAutoField(primary_key=True)
    mutation_id = models.CharField(max_length=255, blank=True, null=True)
    hotspot_mutation = models.BooleanField(blank=True, null=True)
    model_id = models.CharField(max_length=255, blank=True, null=True)
    model_uuid = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "model_mutation_data"


class ModelMutationData(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    species = models.TextField(blank=True, null=True)
    gene_symbol = models.CharField(max_length=255, blank=True, null=True)
    dbsnp_rs = models.CharField(max_length=255, blank=True, null=True)
    mutation_id = models.ForeignKey(
        "ModelMutationFeature",
        to_field="mutation_id",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="mutation_id",
    )
    hotspot_mutation = models.BooleanField(
        db_column="hotspot_mutation", blank=True, null=True
    )  # Field name made lowercase.
    variant_classification = models.TextField(
        db_column="variant_classification", blank=True, null=True
    )  # Field name made lowercase.
    hgvsc = models.TextField(
        db_column="hgvsc", blank=True, null=True
    )  # Field name made lowercase.
    hgvsp_short = models.TextField(
        db_column="hgvsp_short", blank=True, null=True
    )  # Field name made lowercase.
    sift = models.TextField(
        db_column="sift", blank=True, null=True
    )  # Field name made lowercase.
    polyphen = models.TextField(
        db_column="polyphen", blank=True, null=True
    )  # Field name made lowercase.
    data_source = models.TextField(
        db_column="data_source", blank=True, null=True
    )  # Field name made lowercase.

    @property
    def oncokbs(self):
        return OncoKB.objects.filter(
            gene=self.gene_symbol, mutant=self.mutation_id.mutation_id.split(":")[0]
        )

    class Meta:
        managed = False
        db_table = "model_ccle_mutation_data"


class ModelMutationFeature(models.Model):
    id = models.BigAutoField(primary_key=True)
    mutation_id = models.CharField(max_length=255, blank=True, null=True, unique=True)
    gene_symbol = models.CharField(max_length=255, blank=True, null=True)
    aa_mutation = models.CharField(max_length=255, blank=True, null=True)
    species = models.TextField(blank=True, null=True)
    exon_rank = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "model_mutation_feature"


class ModelPathwaySsgseaData(models.Model):
    kegg_pathway_id = models.ForeignKey(
        "PathwayInfoFromKegg",
        to_field="pathway_id",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="kegg_pathway_id",
    )
    # kegg_pathway_id = models.TextField(blank=True, null=True)
    species = models.TextField(blank=True, null=True)
    ssgsea_score = models.FloatField(blank=True, null=True)
    rnaseq_id = models.TextField(blank=True, null=True)
    # cancer_type = models.TextField(blank=True, null=True)
    # model_id = models.TextField(blank=True, null=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    normalized_ssgsea_score = models.FloatField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "model_pathway_ssgsea_data"


class PathwayGeneFromKegg(models.Model):
    id = models.BigAutoField(primary_key=True)
    kegg_pathway_id = models.ForeignKey(
        "PathwayInfoFromKegg",
        to_field="pathway_id",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="kegg_pathway_id",
    )
    gene_symbol = models.CharField(max_length=255, blank=True, null=True)
    kegg_gene_id = models.IntegerField(blank=True, null=True)
    coords = models.CharField(max_length=255, blank=True, null=True)
    shape = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "pathway_gene_from_kegg"


class PathwayInfoFromKegg(models.Model):
    id = models.BigAutoField(primary_key=True)
    pathway_id = models.CharField(max_length=255, blank=True, null=True, unique=True)
    species = models.TextField(blank=True, null=True)
    pathway_name = models.CharField(max_length=255, blank=True, null=True)
    img_path = models.CharField(max_length=255, blank=True, null=True)
    html_string = models.TextField(blank=True, null=True)
    img_height = models.IntegerField(blank=True, null=True)
    img_width = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "pathway_info_from_kegg"


class ProteinDomainMapping(models.Model):
    id = models.BigAutoField(primary_key=True)
    uniprot_id = models.CharField(max_length=255, blank=True, null=True, unique=True)
    domain_id = models.CharField(max_length=255, blank=True, null=True)
    domain_name = models.CharField(max_length=255, blank=True, null=True)
    domain_desc = models.CharField(max_length=255, blank=True, null=True)
    seq_start = models.IntegerField(blank=True, null=True)
    seq_end = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "protein_domain_mapping_v1"


class ProteinSeq(models.Model):
    id = models.BigAutoField(primary_key=True)
    db_source = models.CharField(max_length=255, blank=True, null=True)
    uniprot_id = models.ForeignKey(
        "ProteinDomainMapping",
        to_field="uniprot_id",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="uniprot_id",
        blank=True,
        null=True,
    )
    uniprot_entry = models.CharField(max_length=255, blank=True, null=True)
    protein_name = models.CharField(
        db_column="protein name", max_length=255, blank=True, null=True
    )  # Field renamed to remove unsuitable characters.
    gene_symbol = models.ForeignKey(
        "GeneInfo",
        to_field="symbol",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="gene_symbol",
        blank=True,
        null=True,
    )
    protein_existence = models.IntegerField(blank=True, null=True)
    aa_sequence = models.TextField(blank=True, null=True)
    species = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "protein_seq"


class ModelHlaTyping(models.Model):
    id = models.BigAutoField(primary_key=True)
    rnaseq_id = models.CharField(max_length=255, blank=True, null=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    # model_id = models.CharField(max_length=255, blank=True, null=True)
    hla_class = models.CharField(max_length=255, blank=True, null=True)
    hla_type = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "model_hla_typing"


class ModelTcrBcrData(models.Model):
    rnaseq_id = models.CharField(max_length=255, blank=True, null=True)
    species = models.CharField(max_length=255, blank=True, null=True)
    cdr3_sequence = models.CharField(max_length=255, blank=True, null=True)
    cdr3_aa = models.CharField(max_length=255, blank=True, null=True)
    read_count = models.IntegerField(blank=True, null=True)
    normalized_frequency = models.DecimalField(
        max_digits=12, decimal_places=4, blank=True, null=True
    )
    v_call = models.CharField(max_length=255, blank=True, null=True)
    d_call = models.CharField(max_length=255, blank=True, null=True)
    j_call = models.CharField(max_length=255, blank=True, null=True)
    c_call = models.CharField(max_length=255, blank=True, null=True)
    model_id = models.CharField(max_length=255, blank=True, null=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )

    class Meta:
        managed = False
        db_table = "model_tcr_bcr_data"


class ModelEfficacyInfo(RuleModel):
    id = models.BigAutoField(primary_key=True)
    efficacy_id = models.CharField(max_length=255)
    efficacy_num = models.CharField(max_length=255)
    group_id = models.CharField(max_length=255)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    # model_id = models.CharField(max_length=255, blank=True, null=True)
    passage = models.CharField(max_length=255, blank=True, null=True)
    tumor_fragment = models.CharField(max_length=255, blank=True, null=True)
    route = models.CharField(max_length=255, blank=True, null=True)
    strain = models.CharField(max_length=255, blank=True, null=True)
    sex = models.CharField(max_length=255, blank=True, null=True)
    vendor = models.CharField(max_length=255, blank=True, null=True)
    animal_count = models.CharField(max_length=255, blank=True, null=True)
    tumor_volume_when_starting_treatment = models.DecimalField(
        max_digits=12, decimal_places=4, blank=True, null=True
    )
    drug_name = models.CharField(max_length=255)
    drug_dosage = models.CharField(max_length=255, blank=True, null=True)
    drug_route = models.CharField(max_length=255, blank=True, null=True)
    drug_schedule = models.CharField(max_length=255, blank=True, null=True)
    drug_name_for_bd = models.CharField(max_length=255, blank=True, null=True)
    for_bd = models.CharField(max_length=255, blank=True, null=True)
    for_control = models.CharField(max_length=255, blank=True, null=True)
    for_model = models.BooleanField()
    tgi_tv = models.DecimalField(max_digits=12, decimal_places=4, blank=True, null=True)
    update_date = models.DateField(blank=True, null=True, db_index=True)
    quality = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    push_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    drug_classification = models.CharField(
        max_length=255, blank=True, null=True, db_index=True
    )

    class Meta:
        managed = False
        db_table = "model_efficacy_info"

    @classmethod
    def get_q4user(cls, user, q):
        if user.for_bd:
            return cls.objects.filter(for_db="yes")
        return

    @classmethod
    def get_characterization_queryset(
        cls, user, model_id: str, model_nos: list
    ) -> QuerySet:
        """
        通过user和model_id获取单模型作图所需queryset
        """
        queryset = cls.objects.filter(
            model_uuid__model_id=model_id, for_model=True
        ).filter(user.get_for_bd_q())
        if model_nos:
            queryset.filter(efficacy_num__in=model_nos)
        return queryset.values("efficacy_num", "group_id").order_by(
            "efficacy_num", "group_id"
        )

    @classmethod
    def get_tw_data(cls, user, model_id: str, model_nos: list) -> List[dict]:
        """
        获取tw数据
        """
        return ModelEfficacyTumorWeightData.get4effs(
            model_id, cls.get_characterization_queryset(user, model_id, model_nos)
        )

    @classmethod
    def get_bw_data(cls, user, model_id: str, model_nos: list) -> QuerySet:
        """
        获取bw数据
        """
        return ModelEfficacyBodyWeightGrowthCurveData.get4effs(
            model_id, cls.get_characterization_queryset(user, model_id, model_nos)
        )

    @classmethod
    def get_tv_data(cls, user, model_id: str, model_nos: list) -> QuerySet:
        """
        获取tv数据
        """
        return ModelEfficacyTumorVolumeGrowthCurveData.get4effs(
            model_id, cls.get_characterization_queryset(user, model_id, model_nos)
        )

    @classmethod
    def get_facs_data(cls, user, model_id: str, model_nos: list) -> QuerySet:
        """
        获取facs数据
        """
        return ModelEfficacyFacsGrowthCurveData.get4effs(
            model_id, cls.get_characterization_queryset(user, model_id, model_nos)
        )

    @classmethod
    def get_os_data(cls, user, model_id: str, model_nos: list) -> QuerySet:
        """
        获取os
        """
        return ModelEfficacySurvivalData.get4effs(
            model_id, cls.get_characterization_queryset(user, model_id, model_nos)
        )

    @classmethod
    def get_total_data(cls, user, model_id: str, model_nos: list) -> QuerySet:
        """
        获取total
        """
        return ModelEfficacyTotalFluxData.get4effs(
            model_id, cls.get_characterization_queryset(user, model_id, model_nos)
        )

    @classmethod
    def get_avg_data(cls, user, model_id: str, model_nos: list) -> QuerySet:
        """
        获取avg
        """
        return ModelEfficacyAvgRadianceData.get4effs(
            model_id, cls.get_characterization_queryset(user, model_id, model_nos)
        )

    @classmethod
    def get_image_data(cls, user, model_id: str, model_nos: list) -> QuerySet:
        """
        获取image数据
        """
        return ModelEfficacyImagineData.get4effs(
            model_id, cls.get_characterization_queryset(user, model_id, model_nos)
        )


class ModelIhcImgData(models.Model):
    id = models.BigAutoField(primary_key=True)
    photo_id = models.CharField(max_length=255)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    # model_id = models.ForeignKey('ModelDescInfo', to_field='model_id', on_delete=models.CASCADE, db_constraint=False,
    #                             db_column='model_id'
    passage = models.CharField(max_length=255, blank=True, null=True)
    ffpe_id = models.CharField(max_length=255, blank=True, null=True)
    marker = models.CharField(max_length=255, blank=True, null=True)
    positive_percent = models.CharField(max_length=255, blank=True, null=True)
    positive_grade = models.CharField(max_length=255, blank=True, null=True)
    suffix = models.CharField(max_length=255, blank=True, null=True)
    path = models.CharField(max_length=255, blank=True, null=True)
    tissue = models.CharField(max_length=255, blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    intensity = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "model_ihc_img_data"


class ModelingAttrInfo(RuleModel):
    id = models.BigAutoField(primary_key=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    # model_id = models.CharField(max_length=255, blank=True, null=True)
    group_id = models.CharField(max_length=255)
    amount = models.CharField(max_length=255, blank=True, null=True)
    route = models.CharField(max_length=255, blank=True, null=True)
    strain = models.CharField(max_length=255, blank=True, null=True)
    update_date = models.DateField(blank=True, null=True, db_index=True)
    quality = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    push_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    for_control = models.CharField(max_length=32, blank=True, null=True, db_index=True)
    sex = models.CharField(max_length=255, blank=True, null=True)
    vendor = models.CharField(max_length=255, blank=True, null=True)
    passage = models.CharField(max_length=255, blank=True, null=True)
    days_when_tumor_volume_100mm3 = models.IntegerField(blank=True, null=True)
    days_when_tumor_volume_500mm3 = models.IntegerField(blank=True, null=True)
    days_when_tumor_volume_1000mm3 = models.IntegerField(blank=True, null=True)
    model_no = models.CharField(max_length=255)
    animal_id = models.CharField(max_length=255)
    for_bd = models.CharField(max_length=255, blank=True, null=True)
    for_model = models.BooleanField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "modeling_attr_info"

    @classmethod
    def get_characterization_queryset(
        cls, user, model_id: str, model_nos: list
    ) -> QuerySet:
        queryset = ModelingAttrInfo.objects.filter(
            model_uuid__model_id=model_id
        ).filter(user.get_for_bd_q())
        if model_nos:
            queryset = queryset.filter(model_no__in=model_nos)
        return queryset.values("model_no", "group_id").order_by("model_no", "group_id")

    @classmethod
    def get_tw_data(cls, user, model_id: str, model_nos: list) -> List[dict]:
        """
        获取tw数据
        """
        return ModelingTumorWeightData.get4mods(
            model_id, cls.get_characterization_queryset(user, model_id, model_nos)
        )

    @classmethod
    def get_bw_data(cls, user, model_id: str, model_nos: list) -> QuerySet:
        return ModelingBodyWeightGrowthCurveData.get4mods(
            model_id, cls.get_characterization_queryset(user, model_id, model_nos)
        )

    @classmethod
    def get_tv_data(cls, user, model_id: str, model_nos: list) -> QuerySet:
        return ModelingTumorVolumeGrowthCurveData.get4mods(
            model_id, cls.get_characterization_queryset(user, model_id, model_nos)
        )

    @classmethod
    def get_os_data(cls, user, model_id: str, model_nos: list) -> QuerySet:
        return ModelingSurvivalData.get4mods(
            model_id, cls.get_characterization_queryset(user, model_id, model_nos)
        )

    @classmethod
    def get_total_data(cls, user, model_id: str, model_nos: list) -> QuerySet:
        return ModelingTotalFluxData.get4mods(
            model_id, cls.get_characterization_queryset(user, model_id, model_nos)
        )

    @classmethod
    def get_avg_data(cls, user, model_id: str, model_nos: list) -> QuerySet:
        return ModelingAvgRadianceData.get4mods(
            model_id, cls.get_characterization_queryset(user, model_id, model_nos)
        ).values(
            "group_id",
            "days",
            "date",
            "avg_radiance",
            "model_no",
            model_id=F("model_uuid__model_id"),
        )

    @classmethod
    def get_image_data(cls, user, model_id: str, model_nos: list) -> QuerySet:
        """
        获取image数据
        """
        return ModelEfficacyImagineData.get4mods(
            model_id, cls.get_characterization_queryset(user, model_id, model_nos)
        )


class ClinicalAttrInfo(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    # model_id = models.ForeignKey('ModelDescInfo', to_field='model_id', on_delete=models.CASCADE, db_constraint=False,
    #                             db_column='model_id'
    age = models.IntegerField(blank=True, null=True)
    gender = models.CharField(max_length=255, blank=True, null=True)
    treatment = models.TextField(blank=True, null=True)
    grade = models.CharField(max_length=255, blank=True, null=True)
    histopathology = models.CharField(max_length=255, blank=True, null=True)
    tnm = models.CharField(max_length=255, blank=True, null=True)
    ihc = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "clinical_attr_info"


class ModelHeImgData(models.Model):
    # id = models.BigAutoField(primary_key=True)
    photo_id = models.CharField(max_length=255, primary_key=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    # model_id = models.ForeignKey('ModelDescInfo', to_field='model_id', on_delete=models.CASCADE, db_constraint=False,
    #                             db_column='model_id'
    passage = models.CharField(max_length=255, blank=True, null=True)
    ffpe_id = models.CharField(max_length=255, blank=True, null=True)
    # suffix = models.CharField(max_length=255, blank=True, null=True)
    path = models.CharField(max_length=255, blank=True, null=True)
    for_bd = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "model_he_img_data"

    @property
    def passage_val(self):
        return int(get_numbers(self.passage)[0])


class ModelEfficacyBodyWeightGrowthCurveData(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    model_id = models.CharField(max_length=255, blank=True, null=True)
    efficacy_num = models.CharField(max_length=255, blank=True, null=True)
    group_id = models.CharField(max_length=255, blank=True, null=True)
    animal_id = models.CharField(max_length=255, blank=True, null=True)
    body_part = models.CharField(max_length=255, blank=True, null=True)
    date = models.DateField(blank=True, null=True)
    days = models.IntegerField(blank=True, null=True)
    body_weight = models.DecimalField(
        max_digits=12, decimal_places=4, blank=True, null=True
    )
    avg = models.DecimalField(max_digits=12, decimal_places=4, blank=True, null=True)
    sd = models.DecimalField(max_digits=12, decimal_places=4, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "model_efficacy_body_weight_growth_curve_data"

    @classmethod
    def get4effs(cls, model_id: str, effs: QuerySet) -> QuerySet:
        if not effs:
            return cls.objects.none()
        return (
            cls.objects.filter(
                model_uuid__model_id=model_id,
                efficacy_num__in=[i["efficacy_num"] for i in effs],
                group_id__in=[i["group_id"] for i in effs],
                days__gt=0,
            )
            .values(
                "days",
                "date",
                "body_weight",
                "model_id",
                model_no=F("efficacy_num"),
            )
            .order_by("model_no", "date")
        )


class ModelEfficacyTumorVolumeGrowthCurveData(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    model_id = models.CharField(max_length=255, blank=True, null=True)
    efficacy_num = models.CharField(max_length=255)
    group_id = models.CharField(max_length=255)
    animal_id = models.CharField(max_length=255, blank=True, null=True)
    body_part = models.CharField(max_length=255, blank=True, null=True)
    date = models.DateField(blank=True, null=True)
    days = models.IntegerField(blank=True, null=True)
    tumor_volume = models.DecimalField(
        max_digits=12, decimal_places=4, blank=True, null=True
    )
    update_date = models.DateField(blank=True, null=True)
    push_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    hours = models.IntegerField(blank=True, null=True, db_index=True)
    avg = models.DecimalField(max_digits=12, decimal_places=4, blank=True, null=True)
    sd = models.DecimalField(max_digits=12, decimal_places=4, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "model_efficacy_tumor_volume_growth_curve_data"

    @classmethod
    def get4effs(cls, model_id: str, effs: QuerySet) -> QuerySet:
        if not effs:
            return cls.objects.none()
        return (
            cls.objects.filter(
                model_uuid__model_id=model_id,
                efficacy_num__in=[i["efficacy_num"] for i in effs],
                group_id__in=[i["group_id"] for i in effs],
                days__gt=0,
            )
            .values(
                "days",
                "date",
                "body_part",
                "tumor_volume",
                model_no=F("efficacy_num"),
            )
            .order_by("model_no", "date")
        )


class ModelEfficacyFacsGrowthCurveData(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    model_id = models.CharField(max_length=255, null=True, blank=True)
    group_id = models.CharField(max_length=255)
    animal_id = models.IntegerField(blank=True, null=True)
    date = models.DateField(blank=True, null=True)
    val = models.DecimalField(max_digits=12, decimal_places=4, blank=True, null=True)
    detection_item = models.CharField(max_length=255)
    efficacy_num = models.CharField(max_length=255)
    tissue_type = models.CharField(max_length=255)

    class Meta:
        managed = False
        db_table = "model_efficacy_facs_growth_curve_data"

    @classmethod
    def get4effs(cls, model_id: str, effs: QuerySet) -> QuerySet:
        if not effs:
            return cls.objects.none()
        return (
            cls.objects.filter(
                model_uuid__model_id=model_id,
                efficacy_num__in=[i["efficacy_num"] for i in effs],
                group_id__in=[i["group_id"] for i in effs],
            )
            .values(
                "detection_item",
                "val",
                "group_id",
                "tissue_type",
                "date",
                "model_id",
                model_no=F("efficacy_num"),
            )
            .order_by("model_no", "tissue_type", "group_id", "date")
        )


class ModelEfficacyElisaGrowthCurveData(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    # model_id = models.ForeignKey('ModelDescInfo', to_field='model_id', on_delete=models.CASCADE, db_constraint=False,
    #                             db_column='model_id'
    group_id = models.CharField(max_length=255)
    animal_id = models.IntegerField(blank=True, null=True)
    date = models.DateField(blank=True, null=True)
    val = models.DecimalField(max_digits=12, decimal_places=4, blank=True, null=True)
    detection_item = models.CharField(max_length=255)
    efficacy_num = models.CharField(max_length=255)
    tissue_type = models.CharField(max_length=255)

    class Meta:
        managed = False
        db_table = "model_efficacy_elisa_growth_curve_data"


class ModelingBodyWeightGrowthCurveData(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    model_id = models.CharField(max_length=255, blank=True, null=True)
    group_id = models.CharField(max_length=255)
    animal_id = models.IntegerField(blank=True, null=True)
    body_part = models.CharField(max_length=255, blank=True, null=True)
    date = models.DateField(blank=True, null=True)
    days = models.IntegerField(blank=True, null=True)
    body_weight = models.DecimalField(
        max_digits=12, decimal_places=4, blank=True, null=True
    )
    avg = models.DecimalField(max_digits=12, decimal_places=4, blank=True, null=True)
    sd = models.DecimalField(max_digits=12, decimal_places=4, blank=True, null=True)
    model_no = models.CharField(max_length=255)

    class Meta:
        managed = False
        db_table = "modeling_body_weight_growth_curve_data"

    @classmethod
    def get4mods(cls, model_id: str, mods: QuerySet):
        if not mods:
            return cls.objects.none()
        return (
            cls.objects.filter(
                model_no__in=[i["model_no"] for i in mods],
                group_id__in=[i["group_id"] for i in mods],
                days__gt=0,
                model_uuid__model_id=model_id,
            )
            .values(
                "days",
                "date",
                "body_weight",
                "model_no",
                "model_id",
            )
            .order_by("model_no", "date")
        )


class ModelingTumorVolumeGrowthCurveData(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    model_id = models.CharField(max_length=255, blank=True, null=True)
    group_id = models.CharField(max_length=255)
    animal_id = models.IntegerField(blank=True, null=True)
    body_part = models.CharField(max_length=255, blank=True, null=True)
    date = models.DateField(blank=True, null=True)
    days = models.IntegerField(blank=True, null=True)
    tumor_volume = models.DecimalField(
        max_digits=12, decimal_places=4, blank=True, null=True
    )
    avg = models.DecimalField(max_digits=12, decimal_places=4, blank=True, null=True)
    sd = models.DecimalField(max_digits=12, decimal_places=4, blank=True, null=True)
    model_no = models.CharField(max_length=255)
    push_id = models.CharField(max_length=255, null=True, blank=True)
    hours = models.IntegerField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "modeling_tumor_volume_growth_curve_data"

    @classmethod
    def get4mods(cls, model_id: str, mods: QuerySet) -> QuerySet:
        if not mods:
            return cls.objects.none()
        return (
            cls.objects.filter(
                model_no__in=[i["model_no"] for i in mods],
                group_id__in=[i["group_id"] for i in mods],
                days__gt=0,
                model_uuid__model_id=model_id,
            )
            .values("days", "date", "body_part", "tumor_volume", "model_no")
            .order_by("model_no", "date")
        )


class ModelingFacsGrowthCurveData(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    model_id = models.CharField(max_length=255, blank=True, null=True)
    group_id = models.CharField(max_length=255)
    animal_id = models.IntegerField(blank=True, null=True)
    date = models.DateField(blank=True, null=True)
    val = models.DecimalField(max_digits=12, decimal_places=4, blank=True, null=True)
    detection_item = models.CharField(max_length=255)
    model_no = models.CharField(max_length=255)
    tissue_type = models.CharField(max_length=255)

    class Meta:
        managed = False
        db_table = "modeling_facs_growth_curve_data"

    @classmethod
    def get4mods(cls, model_id: str, mods: QuerySet) -> QuerySet:
        if not mods:
            return cls.objects.none()
        return (
            ModelingFacsGrowthCurveData.objects.filter(
                model_no__in=[i["model_no"] for i in mods],
                group_id__in=[i["group_id"] for i in mods],
                model_uuid__model_id=model_id,
                val__gt=0,
            )
            .values(
                "detection_item",
                "val",
                "group_id",
                "tissue_type",
                "date",
                "model_no",
                "model_id",
            )
            .order_by("model_no", "tissue_type", "group_id", "date")
        )


class ModelingElisaGrowthCurveData(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    group_id = models.CharField(max_length=255, db_column="group_id")
    animal_id = models.IntegerField(blank=True, null=True)
    date = models.DateField(blank=True, null=True)
    val = models.DecimalField(max_digits=12, decimal_places=4, blank=True, null=True)
    detection_item = models.CharField(max_length=255)
    model_no = models.CharField(max_length=255)
    tissue_type = models.CharField(max_length=255)

    class Meta:
        managed = False
        db_table = "modeling_elisa_data"

    @classmethod
    def get4mods(cls, model_id: str, effs: QuerySet) -> QuerySet:
        if not effs:
            return cls.objects.none()
        return (
            cls.objects.filter(
                model_uuid__model_id=model_id,
                tissue_type__icontains="tumor",
                val__gt=0,
            )
            .values(
                "detection_item",
                "val",
                "group_id",
                "tissue_type",
                "model_no",
                "date",
                model_id=F("model_uuid__model_id"),
            )
            .order_by("model_no", "tissue_type", "group_id", "date")
        )


class ModelRnaseqMapping(models.Model):
    model_id = models.TextField(blank=True, null=True)
    rnaseq_id = models.TextField(unique=True, null=True)
    msi_status = models.TextField(blank=True, null=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        related_name="model_rnaseq_mappings",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    id = models.BigAutoField(primary_key=True)
    transcription_level_mutation_count = models.BigIntegerField(blank=True, null=True)
    push_id = models.CharField(max_length=255, blank=True, null=True)
    expressed_tmb = models.FloatField(
        "expressed TMB",
        blank=True,
        null=True,
        help_text="基于转录水平表达的肿瘤突变负荷",
    )
    tumor_purity = models.FloatField(
        "tumor purity(%)", blank=True, null=True, help_text="肿瘤纯度"
    )
    human_derived_sequenced_percentage = models.FloatField(
        "human-derived sequenced percentage(%)",
        blank=True,
        null=True,
        help_text="测序数据的人源比例",
    )

    class Meta:
        managed = False
        db_table = "model_rnaseq_mapping"


class ModelInfoGroup(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
        related_name="model_info_groups",
    )
    # model_id = models.ForeignKey('ModelDescInfo', to_field='model_id', on_delete=models.CASCADE, db_constraint=False,
    #                             db_column='model_id'
    model_information = models.CharField(max_length=255, blank=True, null=True)
    patient_information = models.CharField(max_length=255, blank=True, null=True)
    cell_information = models.CharField(max_length=255, blank=True, null=True)
    growth_charcateristics = models.CharField(max_length=255, blank=True, null=True)
    body_weight_change = models.CharField(max_length=255, blank=True, null=True)
    model_tumor_weight = models.CharField(max_length=255, blank=True, null=True)
    model_total_flux = models.CharField(max_length=255, blank=True, null=True)
    model_avg_radiacne = models.CharField(max_length=255, blank=True, null=True)
    model_survival = models.CharField(max_length=255, blank=True, null=True)
    pathology = models.CharField(max_length=255, blank=True, null=True)
    immunopheneotyping = models.CharField(max_length=255, blank=True, null=True)
    elisa = models.CharField(max_length=255, blank=True, null=True)
    model_img = models.CharField(max_length=255, blank=True, null=True)
    he = models.CharField(max_length=255, blank=True, null=True)
    ihc = models.CharField(max_length=255, blank=True, null=True)
    ihc_io = models.CharField(max_length=255, blank=True, null=True)
    ihc_cd45 = models.CharField(max_length=255, blank=True, null=True)
    tme_immunopheneotyping = models.CharField(max_length=255, blank=True, null=True)
    rna_seq = models.CharField(max_length=255, blank=True, null=True)
    drug_tv = models.CharField(max_length=255, blank=True, null=True)
    drug_bw = models.CharField(max_length=255, blank=True, null=True)
    drug_tw = models.CharField(max_length=255, blank=True, null=True)
    drug_facs = models.CharField(max_length=255, blank=True, null=True)
    drug_elisa = models.CharField(max_length=255, blank=True, null=True)
    drug_total = models.CharField(max_length=255, blank=True, null=True)
    drug_avg = models.CharField(max_length=255, blank=True, null=True)
    drug_survival = models.CharField(max_length=255, blank=True, null=True)
    drug_img = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "model_info_group"


class ModelingTmInfo(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    efficacy_no = models.CharField(max_length=255, blank=True, null=True)
    model_no = models.CharField(max_length=255, blank=True, null=True)
    project_no = models.CharField(max_length=255, blank=True, null=True)
    cell_identification = models.CharField(max_length=255, blank=True, null=True)
    cell_id = models.CharField(max_length=255, blank=True, null=True)
    amount = models.CharField(max_length=255, blank=True, null=True)
    route = models.CharField(max_length=255, blank=True, null=True)
    tumor = models.CharField(max_length=255, blank=True, null=True)
    host = models.CharField(max_length=255, blank=True, null=True)
    strain = models.CharField(max_length=255, blank=True, null=True)
    sex = models.CharField(max_length=255, blank=True, null=True)
    age = models.CharField(max_length=255, blank=True, null=True)
    vendor = models.CharField(max_length=255, blank=True, null=True)
    pbmc = models.CharField(max_length=255, blank=True, null=True)
    pbmc_id = models.CharField(max_length=255, blank=True, null=True)
    pbmc_amount = models.CharField(max_length=255, blank=True, null=True)
    pbmc_route = models.CharField(max_length=255, blank=True, null=True)
    pbmc_schedule = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "modeling_tm_info"


class DbDrugClassification(models.Model):
    push_id = models.CharField(
        primary_key=True, unique=True, max_length=255, blank=True
    )
    name = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "db_drug_classification"


class ModelEfficacyTmInfo(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    efficacy_no = models.CharField(max_length=255, blank=True, null=True)
    model_no = models.CharField(max_length=255, blank=True, null=True)
    project_no = models.CharField(max_length=255, blank=True, null=True)
    cell_identification = models.CharField(max_length=255, blank=True, null=True)
    cell_id = models.CharField(max_length=255, blank=True, null=True)
    amount = models.CharField(max_length=255, blank=True, null=True)
    route = models.CharField(max_length=255, blank=True, null=True)
    tumor = models.CharField(max_length=255, blank=True, null=True)
    host = models.CharField(max_length=255, blank=True, null=True)
    strain = models.CharField(max_length=255, blank=True, null=True)
    sex = models.CharField(max_length=255, blank=True, null=True)
    age = models.CharField(max_length=255, blank=True, null=True)
    vendor = models.CharField(max_length=255, blank=True, null=True)
    pbmc = models.CharField(max_length=255, blank=True, null=True)
    pbmc_id = models.CharField(max_length=255, blank=True, null=True)
    pbmc_amount = models.CharField(max_length=255, blank=True, null=True)
    pbmc_route = models.CharField(max_length=255, blank=True, null=True)
    pbmc_schedule = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "model_efficacy_tm_info"


class ModelEfficacySurvivalData(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    group_id = models.CharField(max_length=255)
    animal_id = models.IntegerField(blank=True, null=True)
    survival = models.DecimalField(
        max_digits=12, decimal_places=4, blank=True, null=True
    )
    efficacy_num = models.CharField(max_length=255)

    class Meta:
        managed = False
        db_table = "model_efficacy_survival_data"

    @classmethod
    def get4effs(cls, model_id: str, effs: QuerySet) -> QuerySet:
        if not effs:
            return cls.objects.none()
        return cls.objects.filter(
            model_uuid__model_id=model_id,
            efficacy_num__in=[i["efficacy_num"] for i in effs],
            group_id__in=[i["group_id"] for i in effs],
        ).values(
            model_no=F("efficacy_num"),
            group=F("group_id"),
            sample=F("animal_id"),
            survival_time=F("survival"),
        )


class ModelEfficacyAvgRadianceData(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    efficacy_num = models.CharField(max_length=255, blank=True, null=True)
    group_id = models.CharField(max_length=255, blank=True, null=True)
    animal_id = models.CharField(max_length=255, blank=True, null=True)
    date = models.DateField(blank=True, null=True)
    days = models.IntegerField(blank=True, null=True)
    avg_radiance = models.DecimalField(
        max_digits=12, decimal_places=4, blank=True, null=True
    )

    class Meta:
        managed = False
        db_table = "model_efficacy_avg_radiance_data"

    @classmethod
    def get4effs(cls, model_id: str, effs: QuerySet) -> QuerySet:
        if not effs:
            return cls.objects.none()
        return (
            cls.objects.filter(
                model_uuid__model_id=model_id,
                efficacy_num__in=[i["efficacy_num"] for i in effs],
                group_id__in=[i["group_id"] for i in effs],
            )
            .values(
                "group_id",
                "days",
                "date",
                "avg_radiance",
                model_no=F("efficacy_num"),
                model_id=F("model_uuid__model_id"),
            )
            .order_by("model_no")
        )


class ModelEfficacyTotalFluxData(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    efficacy_num = models.CharField(max_length=255, blank=True, null=True)
    group_id = models.CharField(max_length=255, blank=True, null=True)
    animal_id = models.CharField(max_length=255, blank=True, null=True)
    date = models.DateField(blank=True, null=True)
    days = models.IntegerField(blank=True, null=True)
    total_flux = models.DecimalField(
        max_digits=12, decimal_places=4, blank=True, null=True
    )

    class Meta:
        managed = False
        db_table = "model_efficacy_total_flux_data"

    @classmethod
    def get4effs(cls, model_id: str, effs: QuerySet) -> QuerySet:
        if not effs:
            return cls.objects.none()
        return cls.objects.filter(
            model_uuid__model_id=model_id,
            efficacy_num__in=[i["efficacy_num"] for i in effs],
            group_id__in=[i["group_id"] for i in effs],
        ).values(
            "group_id",
            "days",
            "date",
            "total_flux",
            model_no=F("efficacy_num"),
            model_id=F("model_uuid__model_id"),
        )


class ModelEfficacyImagineData(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    efficacy_num = models.CharField(max_length=255, blank=True, null=True)
    # model_id = models.CharField(max_length=255, blank=True, null=True)
    path = models.CharField(max_length=255, blank=True, null=True)
    photo_id = models.CharField(max_length=255, blank=True, null=True)
    suffix = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "model_efficacy_imagine_data"

    @classmethod
    def get4effs(cls, model_id: str, effs) -> QuerySet:
        if not effs:
            return cls.objects.none()
        return cls.objects.filter(
            model_uuid__model_id=model_id,
            efficacy_num__in=[i["efficacy_num"] for i in effs],
        ).values("efficacy_num", "path", "photo_id", "suffix")

    @classmethod
    def get4mods(cls, model_id: str, mods) -> QuerySet:
        if not mods:
            return cls.objects.none()
        return cls.objects.filter(
            model_uuid__model_id=model_id,
            efficacy_num__in=[i["model_no"] for i in mods],
        ).values("efficacy_num", "path", "photo_id", "suffix")


class ModelingAvgRadianceData(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    model_no = models.CharField(max_length=255, blank=True, null=True)
    group_id = models.CharField(max_length=255, blank=True, null=True)
    animal_id = models.CharField(max_length=255, blank=True, null=True)
    date = models.DateField(blank=True, null=True)
    days = models.IntegerField(blank=True, null=True)
    avg_radiance = models.DecimalField(
        max_digits=12, decimal_places=4, blank=True, null=True
    )

    class Meta:
        managed = False
        db_table = "modeling_avg_radiance_data"

    @classmethod
    def get4mods(cls, model_id: str, mods: QuerySet) -> QuerySet:
        if not mods:
            return cls.objects.none()
        return cls.objects.filter(
            model_uuid__model_id=model_id,
            model_no__in=[i["model_no"] for i in mods],
            group_id__in=[i["group_id"] for i in mods],
        )


class ModelingTotalFluxData(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    model_no = models.CharField(max_length=255, blank=True, null=True)
    group_id = models.CharField(max_length=255, blank=True, null=True)
    animal_id = models.CharField(max_length=255, blank=True, null=True)
    date = models.DateField(blank=True, null=True)
    days = models.IntegerField(blank=True, null=True)
    total_flux = models.DecimalField(
        max_digits=12, decimal_places=4, blank=True, null=True
    )

    class Meta:
        managed = False
        db_table = "modeling_total_flux_data"

    @classmethod
    def get4mods(cls, model_id: str, mods: QuerySet) -> QuerySet:
        if not mods:
            return cls.objects.none()
        return cls.objects.filter(
            model_no__in=[i["model_no"] for i in mods],
            group_id__in=[i["group_id"] for i in mods],
            model_uuid__model_id=model_id,
        ).values(
            "group_id",
            "days",
            "date",
            "total_flux",
            "model_no",
            model_id=F("model_uuid__model_id"),
        )


class ModelingSurvivalData(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    group_id = models.CharField(max_length=255)
    animal_id = models.IntegerField(blank=True, null=True)
    survival = models.DecimalField(
        max_digits=12, decimal_places=4, blank=True, null=True
    )
    model_no = models.CharField(max_length=255)

    class Meta:
        managed = False
        db_table = "modeling_survival_data"

    @classmethod
    def get4mods(cls, model_id: str, mods: QuerySet) -> QuerySet:
        if not mods:
            return cls.objects.none()
        return cls.objects.filter(
            model_uuid__model_id=model_id,
            model_no__in=[i["model_no"] for i in mods],
            group_id__in=[i["group_id"] for i in mods],
        ).values(
            "model_no",
            group=F("group_id"),
            sample=F("animal_id"),
            survival_time=F("survival"),
        )


class ModelingTumorWeightData(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    group_id = models.CharField(max_length=255, db_column="group_id")
    animal_id = models.IntegerField(blank=True, null=True)
    date = models.DateField(blank=True, null=True)
    tumor_weight = models.DecimalField(
        max_digits=12, decimal_places=4, blank=True, null=True
    )
    model_no = models.CharField(max_length=255)

    class Meta:
        managed = False
        db_table = "modeling_tumor_weight_data"

    @classmethod
    def get4mods(cls, model_id: str, modeling_attr_infos: QuerySet) -> List[dict]:
        data = []
        if not modeling_attr_infos:
            return data
        return [
            {
                "tumor_weight": i.tumor_weight,
                "group_id": i.group_id,
                "date": i.date,
                "days": i.days,
                "model_no": i.model_no,
                "model_id": i.model_uuid.model_id,
            }
            for i in cls.objects.filter(
                model_no__in=[i["model_no"] for i in modeling_attr_infos],
                group_id__in=[i["group_id"] for i in modeling_attr_infos],
                model_uuid__model_id=model_id,
            )
            .all()
            .order_by("model_no", "group_id", "date")
        ]

    @property
    def _query(self) -> Q:
        return Q(
            model_uuid=self.model_uuid,
            group_id=self.group_id,
            model_no=self.model_no,
            date=self.date,
            animal_id=self.animal_id,
        )

    @property
    def bw(self) -> ModelingBodyWeightGrowthCurveData:
        """
        获取对应的modeling_body_weight_data实例
        """
        return ModelingBodyWeightGrowthCurveData.objects.filter(self._query).first()

    @property
    def tv(self) -> ModelingTumorVolumeGrowthCurveData:
        """
        获取对应的modeling_tumor_volume_data实例
        """
        return ModelingTumorVolumeGrowthCurveData.objects.filter(self._query).first()

    @property
    def days(self):
        """
        获取days时间
        """
        data = self.bw or self.tv
        return data.days if data else None


class ModelEfficacyTumorWeightData(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    group_id = models.CharField(max_length=255, db_column="group_id")
    animal_id = models.IntegerField(blank=True, null=True)
    date = models.DateField(blank=True, null=True)
    tumor_weight = models.DecimalField(
        max_digits=12, decimal_places=4, blank=True, null=True
    )
    efficacy_num = models.CharField(max_length=255)

    class Meta:
        managed = False
        db_table = "model_efficacy_tumor_weight_data"

    @classmethod
    def get4effs(cls, model_id: str, model_efficacy_infos: QuerySet) -> List[dict]:
        """
        通过model_efficacy_info的查询集和model_id筛选tw作图所需queryset
        """
        data = []
        if not model_efficacy_infos:
            return data

        for i in (
            cls.objects.filter(
                Q(
                    model_uuid__model_id=model_id,
                    efficacy_num__in=[i["efficacy_num"] for i in model_efficacy_infos],
                    group_id__in=[i["group_id"] for i in model_efficacy_infos],
                )
            )
            .all()
            .order_by("efficacy_num", "group_id", "date")
        ):
            data.append(
                {
                    "tumor_weight": i.tumor_weight,
                    "group_id": i.group_id,
                    "date": i.date,
                    "days": i.days,
                    "model_no": i.efficacy_num,
                    "model_id": i.model_uuid.model_id,
                }
            )
        return data

    @property
    def _query(self) -> Q:
        return Q(
            model_uuid=self.model_uuid,
            efficacy_num=self.efficacy_num,
            group_id=self.group_id,
            date=self.date,
            animal_id=self.animal_id,
        )

    @property
    def bw(self) -> ModelEfficacyBodyWeightGrowthCurveData:
        """
        获取对应的bw数据
        """
        return ModelEfficacyBodyWeightGrowthCurveData.objects.filter(
            self._query
        ).first()

    @property
    def tv(self) -> ModelEfficacyTumorVolumeGrowthCurveData:
        """
        获取对应的tv数据
        """
        return ModelEfficacyTumorVolumeGrowthCurveData.objects.filter(
            self._query
        ).first()

    @property
    def days(self):
        data = self.bw or self.tv
        return data.days if data else None


class ModelEfficacyTGITVData(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    group_id = models.CharField(max_length=255, db_column="group_id")
    date = models.DateField(blank=True, null=True)
    days = models.IntegerField(blank=True, null=True)
    tgi = models.DecimalField(max_digits=12, decimal_places=4, blank=True, null=True)
    efficacy_num = models.CharField(max_length=255)

    class Meta:
        managed = False
        db_table = "model_efficacy_tgi_tv_data"


class ModelEfficacyTGITWData(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    group_id = models.CharField(max_length=255, db_column="group_id")
    date = models.DateField(blank=True, null=True)
    days = models.IntegerField(blank=True, null=True)
    tgi = models.DecimalField(max_digits=12, decimal_places=4, blank=True, null=True)
    efficacy_num = models.CharField(max_length=255)

    class Meta:
        managed = False
        db_table = "model_efficacy_tgi_tw_data"


class ModelEfficacyPanelData(models.Model):
    id = models.BigAutoField(primary_key=True)
    panel = models.CharField(max_length=255, blank=True, null=True)
    detection_item = models.CharField(max_length=255, blank=True, null=True)
    efficacy_num = models.CharField(max_length=255, blank=True, null=True)
    update_date = models.DateField(null=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    push_id = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "model_efficacy_panel_data"


class ModelingPanelData(models.Model):
    id = models.BigAutoField(primary_key=True)
    panel = models.CharField(max_length=255, blank=True, null=True)
    detection_item = models.CharField(max_length=255, blank=True, null=True)
    model_no = models.CharField(max_length=255, blank=True, null=True)
    update_date = models.DateField(null=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    push_id = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "modeling_panel_data"


class ModelIhcTableData(models.Model):
    # id = models.BigAutoField(primary_key=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    passage = models.CharField(max_length=255, blank=True, null=True)
    model_id = models.CharField(max_length=255, blank=True, null=True)
    animal_strain = models.CharField(max_length=255, blank=True, null=True)
    ffpe = models.CharField(max_length=255, blank=True, null=True)
    marker = models.CharField(max_length=255, blank=True, null=True)
    marker_compartment = models.CharField(max_length=255, blank=True, null=True)
    positive_cell_type = models.CharField(max_length=255, blank=True, null=True)
    positive_intensity = models.CharField(max_length=255, blank=True, null=True)
    h_score = models.CharField(max_length=255, blank=True, null=True)
    positive_control_img = models.CharField(max_length=255, blank=True, null=True)
    marker_compute_name_img = models.CharField(max_length=255, blank=True, null=True)
    isotype_compute_name_img = models.CharField(max_length=255, blank=True, null=True)
    he_compute_name_img = models.CharField(max_length=255, blank=True, null=True)
    for_bd = models.BooleanField(blank=True, null=True)
    update_date = models.DateField(null=True)
    push_id = models.CharField(max_length=255, blank=True, null=True)
    positive_region = models.CharField(max_length=255, blank=True, null=True)
    positive_control = models.CharField(max_length=255, blank=True, null=True)
    he_compute_name = models.CharField(max_length=255, blank=True, null=True)
    marker_compute_name = models.CharField(max_length=255, blank=True, null=True)
    isotype_compute_name = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "model_ihc_table_data"

    @property
    def passage_val(self):
        return int(get_numbers(self.passage)[0])


class ModelInfoGroupForAll(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    model_information = models.CharField(max_length=255, blank=True, null=True)
    patient_information = models.CharField(max_length=255, blank=True, null=True)
    cell_information = models.CharField(max_length=255, blank=True, null=True)
    growth_charcateristics = models.CharField(max_length=255, blank=True, null=True)
    body_weight_change = models.CharField(max_length=255, blank=True, null=True)
    model_tumor_weight = models.CharField(max_length=255, blank=True, null=True)
    model_total_flux = models.CharField(max_length=255, blank=True, null=True)
    model_avg_radiacne = models.CharField(max_length=255, blank=True, null=True)
    model_survival = models.CharField(max_length=255, blank=True, null=True)
    pathology = models.CharField(max_length=255, blank=True, null=True)
    immunopheneotyping = models.CharField(max_length=255, blank=True, null=True)
    elisa = models.CharField(max_length=255, blank=True, null=True)
    model_img = models.CharField(max_length=255, blank=True, null=True)
    he = models.CharField(max_length=255, blank=True, null=True)
    ihc = models.CharField(max_length=255, blank=True, null=True)
    ihc_io = models.CharField(max_length=255, blank=True, null=True)
    ihc_cd45 = models.CharField(max_length=255, blank=True, null=True)
    tme_immunopheneotyping = models.CharField(max_length=255, blank=True, null=True)
    rna_seq = models.CharField(max_length=255, blank=True, null=True)
    drug_tv = models.CharField(max_length=255, blank=True, null=True)
    drug_bw = models.CharField(max_length=255, blank=True, null=True)
    drug_tw = models.CharField(max_length=255, blank=True, null=True)
    drug_facs = models.CharField(max_length=255, blank=True, null=True)
    drug_elisa = models.CharField(max_length=255, blank=True, null=True)
    drug_total = models.CharField(max_length=255, blank=True, null=True)
    drug_avg = models.CharField(max_length=255, blank=True, null=True)
    drug_survival = models.CharField(max_length=255, blank=True, null=True)
    drug_img = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "model_info_group_for_all"


class ModelingPathologyData(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_no = models.CharField(max_length=255, blank=True, null=True)
    group_id = models.CharField(max_length=255, blank=True, null=True)
    animal_id = models.CharField(max_length=255, blank=True, null=True)
    detection_item = models.CharField(max_length=255, blank=True, null=True)
    val = models.FloatField(blank=True, null=True)
    update_date = models.DateField(blank=True, null=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    push_id = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "modeling_pathology_data"


class ModelIhcIoTableData(models.Model):
    id = models.BigAutoField(primary_key=True)
    path = models.CharField(max_length=255, blank=True, null=True)
    for_bd = models.CharField(max_length=255, blank=True, null=True)
    update_date = models.DateField(null=True)
    model_id = models.CharField(max_length=255, blank=True, null=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    push_id = models.CharField(max_length=255, blank=True, null=True)
    height = models.FloatField(null=True)
    width = models.FloatField(null=True)

    class Meta:
        managed = False
        db_table = "model_ihc_io_table_data"
        ordering = ["model_id"]


class ModelHeTableData(models.Model):
    id = models.BigAutoField(primary_key=True)
    passage = models.CharField(max_length=255, blank=True, null=True)
    animal_strain = models.CharField(max_length=255, blank=True, null=True)
    ffpe = models.CharField(max_length=255, blank=True, null=True)
    protocol_no = models.CharField(max_length=255, blank=True, null=True)
    cancer_site = models.CharField(max_length=255, blank=True, null=True)
    split_apart = models.CharField(max_length=255, blank=True, null=True)
    pathotyping = models.CharField(max_length=255, blank=True, null=True)
    special_structure = models.CharField(max_length=255, blank=True, null=True)
    invasive = models.CharField(max_length=255, blank=True, null=True)
    matching = models.CharField(max_length=255, blank=True, null=True)
    comment = models.CharField(max_length=255, blank=True, null=True)
    path = models.CharField(max_length=255, blank=True, null=True)
    for_bd = models.CharField(max_length=255, blank=True, null=True)
    update_date = models.TextField(blank=True, null=True)
    model_id = models.CharField(max_length=255, blank=True, null=True)
    model_uuid = models.ForeignKey(
        "ModelDescInfo",
        to_field="model_uuid",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_column="model_uuid",
    )
    push_id = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "model_he_table_data"
        ordering = ["model_id"]


class ModelSignatureScore(models.Model):
    id = models.BigAutoField(primary_key=True)
    index = models.CharField(
        "指标", max_length=100, null=True, blank=True, db_index=True
    )
    medicinal_efficacy = models.CharField(
        "药效", max_length=100, blank=True, null=True, db_index=True
    )
    score = models.FloatField("得分", blank=True, null=True)
    model_id = models.CharField(
        "ModelID", max_length=255, blank=True, null=True, db_index=True
    )
    model_uuid = models.UUIDField("model_uuid", blank=True, null=True, db_index=True)

    class Meta:
        db_table = "model_signature_score"
        ordering = ["model_id"]

    @property
    def model_desc_info(self) -> ModelDescInfo:
        return ModelDescInfo.objects.filter(model_uuid=self.model_uuid).first()


class MModelDescInfo(models.Model):
    model_id = models.CharField(max_length=255, blank=True, null=True, unique=True)
    model_uuid = models.CharField(primary_key=True, max_length=255, unique=True)
    rnaseq_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    model_type = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    verbose_model_type = models.CharField(
        max_length=255, blank=True, null=True, db_index=True
    )
    model_name = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    cancer_type = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    verbose_cancer_type = models.CharField(
        max_length=255, blank=True, null=True, db_index=True
    )
    msi_status = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    cancer_subtype_short_names = models.CharField(
        max_length=255, blank=True, null=True, db_index=True
    )
    model_name_outer = models.CharField(
        max_length=255, blank=True, null=True, db_index=True
    )
    second_model_type = models.CharField(
        max_length=255, blank=True, null=True, db_index=True
    )
    verbose_second_model_type = models.CharField(
        max_length=255, blank=True, null=True, db_index=True
    )
    ccle_line = models.CharField(max_length=150, blank=True, null=True, db_index=True)
    ccle_stripped_cell_line_name = models.CharField(
        max_length=150, blank=True, null=True, db_index=True
    )
    ccle_id = models.TextField(blank=True, null=True)
    transcription_level_mutation_count = models.BigIntegerField(
        blank=True, null=True, db_index=True
    )
    is_cancer_model = models.BooleanField(db_index=True)
    has_info = models.BooleanField(default=False, db_index=True)
    has_drug_info = models.BooleanField(default=False, db_index=True)
    verbose_in_vivo_pharmacology_model_types = models.JSONField(
        "体内药理模型分类中文",
        max_length=255,
        blank=True,
        null=True,
        default=list,
        db_index=True,
    )
    is_usable = models.BooleanField(default=False, db_index=True)

    class Meta:
        db_table = "m_model_desc_info"
        ordering = ["model_id"]


class MModelInfoGroup(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_id = models.CharField(max_length=255, blank=True, null=True, unique=True)
    model_desc_info = models.OneToOneField(
        MModelDescInfo, on_delete=models.CASCADE, db_column="model_uuid"
    )
    model_information = models.BooleanField(default=False, db_index=True)
    patient_information = models.BooleanField(default=False, db_index=True)
    cell_information = models.BooleanField(default=False, db_index=True)
    growth_charcateristics = models.BooleanField(default=False, db_index=True)
    body_weight_change = models.BooleanField(default=False, db_index=True)
    model_tumor_weight = models.BooleanField(default=False, db_index=True)
    model_total_flux = models.BooleanField(default=False, db_index=True)
    model_avg_radiacne = models.BooleanField(default=False, db_index=True)
    model_survival = models.BooleanField(default=False, db_index=True)
    pathology = models.BooleanField(default=False, db_index=True)
    immunopheneotyping = models.BooleanField(default=False, db_index=True)
    elisa = models.BooleanField(default=False, db_index=True)
    model_img = models.BooleanField(default=False, db_index=True)
    he = models.BooleanField(default=False, db_index=True)
    ihc = models.BooleanField(default=False, db_index=True)
    ihc_io = models.BooleanField(default=False, db_index=True)
    ihc_cd45 = models.BooleanField(default=False, db_index=True)
    tme_immunopheneotyping = models.BooleanField(default=False, db_index=True)
    rna_seq = models.BooleanField(default=False, db_index=True)
    drug_tv = models.BooleanField(default=False, db_index=True)
    drug_bw = models.BooleanField(default=False, db_index=True)
    drug_tw = models.BooleanField(default=False, db_index=True)
    drug_facs = models.BooleanField(default=False, db_index=True)
    drug_elisa = models.BooleanField(default=False, db_index=True)
    drug_total = models.BooleanField(default=False, db_index=True)
    drug_avg = models.BooleanField(default=False, db_index=True)
    drug_survival = models.BooleanField(default=False, db_index=True)
    drug_img = models.BooleanField(default=False, db_index=True)
    has_info = models.BooleanField(default=False, db_index=True)
    has_drug_info = models.BooleanField(default=False, db_index=True)
    is_usable = models.BooleanField(default=False, db_index=True)

    class Meta:
        db_table = "m_model_info_group"
        ordering = ["id"]

    def update_has_info(self):
        self.has_info = any(
            [
                self.model_information,
                self.patient_information,
                self.cell_information,
                self.growth_charcateristics,
                self.body_weight_change,
                self.model_tumor_weight,
                self.model_total_flux,
                self.model_avg_radiacne,
                self.model_survival,
                self.pathology,
                self.immunopheneotyping,
                self.elisa,
                self.model_img,
                self.he,
                self.ihc,
                self.ihc_io,
                self.ihc_cd45,
                self.tme_immunopheneotyping,
                self.rna_seq,
                self.drug_tv,
                self.drug_bw,
                self.drug_tw,
                self.drug_facs,
                self.drug_elisa,
                self.drug_total,
                self.drug_avg,
                self.drug_survival,
                self.drug_img,
            ]
        )

    def update_is_usable(self):
        self.is_usable = any(
            [
                self.patient_information,
                self.cell_information,
                self.growth_charcateristics,
                self.body_weight_change,
                self.model_tumor_weight,
                self.model_total_flux,
                self.model_avg_radiacne,
                self.model_survival,
                self.pathology,
                self.immunopheneotyping,
                self.elisa,
                self.he,
                self.ihc,
                self.tme_immunopheneotyping,
                self.drug_tv,
                self.drug_bw,
                self.drug_tw,
                self.drug_facs,
                self.drug_elisa,
                self.drug_total,
                self.drug_avg,
                self.drug_survival,
                self.drug_img,
            ]
        )

    def update_has_drug_info(self):
        self.has_drug_info = any(
            [
                self.drug_tv,
                self.drug_bw,
                self.drug_tw,
                self.drug_facs,
                self.drug_elisa,
                self.drug_total,
                self.drug_avg,
                self.drug_survival,
                self.drug_img,
            ]
        )


class MModelEfficacyInfo(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    model_desc_info = models.ForeignKey(
        MModelDescInfo, on_delete=models.CASCADE, db_column="model_uuid", db_index=True
    )
    passage = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    tumor_fragment = models.CharField(
        max_length=255, blank=True, null=True, db_index=True
    )
    route = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    strain = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    sex = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    vendor = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    efficacy_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    efficacy_num = models.CharField(
        max_length=255, blank=True, null=True, db_index=True
    )
    group_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    animal_count = models.IntegerField(blank=True, null=True, db_index=True)
    tumor_volume_when_starting_treatment = models.CharField(
        max_length=255, blank=True, null=True, db_index=True
    )
    drug_name = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    drug_dosage = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    drug_route = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    drug_schedule = models.CharField(
        max_length=255, blank=True, null=True, db_index=True
    )
    update_date = models.DateField(blank=True, null=True, db_index=True)
    drug_name_for_bd = models.CharField(
        max_length=255, blank=True, null=True, db_index=True
    )
    quality = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    for_bd = models.BooleanField(default=False, db_index=True)
    push_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    for_control = models.CharField(max_length=32, blank=True, null=True, db_index=True)
    for_model = models.BooleanField(default=False, db_index=True)
    tgi_tv = models.FloatField(default=0.0, blank=True, null=True, db_index=True)
    drug_classification = models.CharField(
        max_length=255, blank=True, null=True, db_index=True
    )
    is_alone = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "m_model_efficacy_info"
        ordering = ["model_id"]

    @classmethod
    def get_characterization_queryset(cls, model_id: str) -> QuerySet:
        queryset = cls.objects.filter(
            model_uuid__model_id=model_id, for_model=True, for_bd=True
        )
        return queryset.values("efficacy_num", "group_id").order_by(
            "efficacy_num", "group_id"
        )

    @classmethod
    def get_tw_data(cls, model_id) -> List[dict]:
        """
        获取tw数据
        """
        return ModelEfficacyTumorWeightData.get4effs(
            model_id, cls.get_characterization_queryset(model_id)
        )


class MModelingAttrInfo(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    model_desc_info = models.ForeignKey(
        MModelDescInfo, on_delete=models.CASCADE, db_column="model_uuid", db_index=True
    )
    group_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    amount = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    route = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    strain = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    sex = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    vendor = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    passage = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    days_when_tumor_volume_100mm3 = models.IntegerField(
        default=0, null=True, db_index=True
    )
    days_when_tumor_volume_500mm3 = models.IntegerField(
        default=0, null=True, db_index=True
    )
    days_when_tumor_volume_1000mm3 = models.IntegerField(
        default=0, null=True, db_index=True
    )
    model_no = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    update_date = models.DateField(blank=True, null=True, db_index=True)
    quality = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    for_bd = models.BooleanField(default=False, db_index=True)
    animal_id = models.IntegerField(null=True, db_index=True)
    push_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    for_control = models.CharField(max_length=32, blank=True, null=True, db_index=True)
    for_model = models.BooleanField(default=False, db_index=True)

    class Meta:
        db_table = "m_modeling_attr_info"
        ordering = ["model_id"]

    @classmethod
    def get_characterization_queryset(cls, model_id: str) -> QuerySet:
        queryset = cls.objects.filter(model_id=model_id, for_bd=True)
        return queryset.values("model_no", "group_id").order_by("model_no", "group_id")

    @classmethod
    def get_tw_data(cls, model_id: str) -> List[dict]:
        """
        获取tw数据
        """
        return ModelingTumorWeightData.get4mods(
            model_id, cls.get_characterization_queryset(model_id)
        )

    @staticmethod
    def get_result4plot(data: List[dict]):
        model_no_index_dct = {}
        result = []
        index = 0
        for i in data:
            model_no = i["model_no"]
            single_data = {
                "detection_item": i["group_id"],
                "model_id_no": "Tumor Weight",
                "tissue_type": "Tumor Weight(g)",
                "date": f'PG-D{i["days"]}',
                "val": round(i["tumor_weight"], 4),
            }
            if model_no not in model_no_index_dct:
                model_no_index_dct[i["model_no"]] = index
                index += 1
                result.append({"key": model_no, "val": [single_data]})
            else:
                result[model_no_index_dct[model_no]]["val"].append(single_data)
        return result


class MModelingTumorVolumeGrowthCurveData(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    model_desc_info = models.ForeignKey(
        MModelDescInfo, on_delete=models.CASCADE, db_column="model_uuid", db_index=True
    )
    group_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    animal_id = models.IntegerField(blank=True, null=True, db_index=True)
    body_part = models.CharField(max_length=255, blank=True, null=True)
    date = models.DateField(blank=True, null=True, db_index=True)
    days = models.IntegerField(blank=True, null=True, db_index=True)
    tumor_volume = models.FloatField(blank=True, null=True)
    avg = models.FloatField(blank=True, null=True)
    sd = models.FloatField(blank=True, null=True)
    model_no = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    push_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    hours = models.IntegerField(blank=True, null=True, db_index=True)

    class Meta:
        db_table = "m_modeling_tumor_volume_growth_curve_data"
        ordering = ["model_id"]


class MModelEfficacyTumorVolumeGrowthCurveData(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    model_desc_info = models.ForeignKey(
        MModelDescInfo, on_delete=models.CASCADE, db_column="model_uuid", db_index=True
    )
    efficacy_num = models.CharField(
        max_length=255, null=True, blank=True, db_index=True
    )
    group_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    animal_id = models.CharField(max_length=255, blank=True, null=True)
    body_part = models.CharField(max_length=255, blank=True, null=True)
    date = models.DateField(blank=True, null=True)
    days = models.IntegerField(blank=True, null=True, db_index=True)
    tumor_volume = models.FloatField(blank=True, null=True)
    avg = models.FloatField(blank=True, null=True)
    sd = models.FloatField(blank=True, null=True)
    update_date = models.DateField(blank=True, null=True)
    push_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    hours = models.IntegerField(blank=True, null=True, db_index=True)

    class Meta:
        db_table = "m_model_efficacy_tumor_volume_growth_curve_data"
        ordering = ["model_id"]


class TVStats(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    model_desc_info = models.ForeignKey(
        MModelDescInfo, on_delete=models.CASCADE, db_column="model_uuid", db_index=True
    )
    model_no = models.CharField(max_length=32, null=True, blank=True, db_index=True)
    group_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    date = models.DateField(blank=True, null=True, db_index=True)
    days = models.IntegerField(blank=True, null=True, db_index=True)
    count = models.IntegerField("count")
    mean = models.FloatField("mean")
    std = models.FloatField("std")
    confidence_interval_lower_bound = models.FloatField("置信区间下界")
    confidence_interval_upper_bound = models.FloatField("置信区间上界")
    type = models.CharField("类型", max_length=32, db_index=True)
    drug_name = models.CharField(max_length=100, default="", db_index=True)
    bd_drug_name = models.CharField(max_length=100, default="", db_index=True)

    class Meta:
        db_table = "tv_stats"
        ordering = ["model_id", "model_no", "days", "type", "group_id"]


class BWStats(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    model_desc_info = models.ForeignKey(
        MModelDescInfo, on_delete=models.CASCADE, db_column="model_uuid", db_index=True
    )
    model_no = models.CharField(max_length=32, null=True, blank=True, db_index=True)
    group_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    date = models.DateField(blank=True, null=True, db_index=True)
    days = models.IntegerField(blank=True, null=True, db_index=True)
    count = models.IntegerField("count")
    mean = models.FloatField("mean")
    std = models.FloatField("std")
    confidence_interval_lower_bound = models.FloatField("置信区间下界")
    confidence_interval_upper_bound = models.FloatField("置信区间上界")
    type = models.CharField("类型", max_length=32, db_index=True)
    drug_name = models.CharField(max_length=100, default="", db_index=True)
    bd_drug_name = models.CharField(max_length=100, default="", db_index=True)

    class Meta:
        db_table = "bw_stats"
        ordering = ["model_id", "model_no", "days", "type", "group_id"]


class FluxStats(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    model_desc_info = models.ForeignKey(
        MModelDescInfo, on_delete=models.CASCADE, db_column="model_uuid", db_index=True
    )
    model_no = models.CharField(max_length=32, null=True, blank=True, db_index=True)
    group_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    date = models.DateField(blank=True, null=True, db_index=True)
    days = models.IntegerField(blank=True, null=True, db_index=True)
    count = models.IntegerField("count")
    mean = models.FloatField("mean")
    std = models.FloatField("std")
    confidence_interval_lower_bound = models.FloatField("置信区间下界")
    confidence_interval_upper_bound = models.FloatField("置信区间上界")
    type = models.CharField("类型", max_length=32, db_index=True)
    drug_name = models.CharField(max_length=100, default="", db_index=True)
    bd_drug_name = models.CharField(max_length=100, default="", db_index=True)

    class Meta:
        db_table = "flux_stats"
        ordering = ["model_id", "type", "model_no", "days", "group_id"]


class AvgStats(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    model_desc_info = models.ForeignKey(
        MModelDescInfo, on_delete=models.CASCADE, db_column="model_uuid", db_index=True
    )
    model_no = models.CharField(max_length=32, null=True, blank=True, db_index=True)
    group_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    date = models.DateField(blank=True, null=True, db_index=True)
    days = models.IntegerField(blank=True, null=True, db_index=True)
    count = models.IntegerField("count")
    mean = models.FloatField("mean")
    std = models.FloatField("std")
    confidence_interval_lower_bound = models.FloatField("置信区间下界")
    confidence_interval_upper_bound = models.FloatField("置信区间上界")
    type = models.CharField("类型", max_length=32, db_index=True)
    drug_name = models.CharField(max_length=100, default="", db_index=True)
    bd_drug_name = models.CharField(max_length=100, default="", db_index=True)

    class Meta:
        db_table = "avg_stats"
        ordering = ["model_id", "type", "model_no", "days", "group_id"]


class HE(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    model_desc_info = models.ForeignKey(
        MModelDescInfo, on_delete=models.CASCADE, db_column="model_uuid", db_index=True
    )
    passage = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    animal_strain = models.CharField(max_length=255, blank=True, null=True)
    ffpe = models.CharField(max_length=255, blank=True, null=True)
    protocol_no = models.CharField(max_length=255, blank=True, null=True)
    cancer_site = models.CharField(max_length=255, blank=True, null=True)
    split_apart = models.CharField(max_length=255, blank=True, null=True)
    pathotyping = models.CharField(max_length=255, blank=True, null=True)
    special_structure = models.CharField(max_length=255, blank=True, null=True)
    invasive = models.CharField(max_length=255, blank=True, null=True)
    matching = models.CharField(max_length=255, blank=True, null=True)
    comment = models.CharField(max_length=255, blank=True, null=True)
    path = models.CharField(max_length=255, blank=True, null=True)
    for_bd = models.BooleanField(default=False, db_index=True)
    update_date = models.TextField(blank=True, null=True)
    push_id = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = "he"
        ordering = ["model_id", "passage"]


class IHC(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_id = models.CharField(max_length=255, blank=True, null=True)
    model_desc_info = models.ForeignKey(
        MModelDescInfo, on_delete=models.CASCADE, db_column="model_uuid", db_index=True
    )
    passage = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    animal_strain = models.CharField(max_length=255, blank=True, null=True)
    ffpe = models.CharField(max_length=255, blank=True, null=True)
    marker = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    marker_compartment = models.CharField(max_length=255, blank=True, null=True)
    positive_cell_type = models.CharField(max_length=255, blank=True, null=True)
    positive_intensity = models.CharField(max_length=255, blank=True, null=True)
    h_score = models.CharField(max_length=255, blank=True, null=True)
    positive_control_img = models.CharField(max_length=255, blank=True, null=True)
    marker_compute_name_img = models.CharField(max_length=255, blank=True, null=True)
    isotype_compute_name_img = models.CharField(max_length=255, blank=True, null=True)
    he_compute_name_img = models.CharField(max_length=255, blank=True, null=True)
    for_bd = models.BooleanField(default=False, db_index=True)
    update_date = models.DateField(null=True)
    push_id = models.IntegerField(blank=True, null=True)
    positive_region = models.CharField(max_length=255, blank=True, null=True)
    positive_control = models.CharField(max_length=255, blank=True, null=True)
    he_compute_name = models.CharField(max_length=255, blank=True, null=True)
    marker_compute_name = models.CharField(max_length=255, blank=True, null=True)
    isotype_compute_name = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = "ihc"
        ordering = ["model_id", "marker"]


class IHCIO(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    model_desc_info = models.ForeignKey(
        MModelDescInfo, on_delete=models.CASCADE, db_column="model_uuid", db_index=True
    )
    path = models.CharField(max_length=255, blank=True, null=True)
    for_bd = models.BooleanField(default=False, db_index=True)
    update_date = models.DateField(null=True)
    push_id = models.CharField(max_length=255, blank=True, null=True)
    height = models.FloatField(null=True)
    width = models.FloatField(null=True)

    class Meta:
        db_table = "ihc_io"
        ordering = ["model_id"]


class MModelEfficacyImagineData(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_desc_info = models.ForeignKey(
        MModelDescInfo, on_delete=models.CASCADE, db_column="model_uuid", db_index=True
    )
    model_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    efficacy_num = models.CharField(
        max_length=255, blank=True, null=True, db_index=True
    )
    path = models.CharField(max_length=255, blank=True, null=True)
    photo_id = models.CharField(max_length=255, blank=True, null=True)
    suffix = models.CharField(max_length=255, blank=True, null=True)
    for_bd = models.BooleanField(blank=True, null=True, db_index=True)
    for_model = models.BooleanField(blank=True, null=True, db_index=True)
    type = models.CharField(max_length=32, blank=True, null=True, db_index=True)

    class Meta:
        db_table = "m_model_efficacy_imagine_data"
        ordering = ["model_desc_info", "efficacy_num"]


class MModelingFacsGrowthCurveData(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_desc_info = models.ForeignKey(
        MModelDescInfo, on_delete=models.CASCADE, db_column="model_uuid", db_index=True
    )
    model_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    group_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    animal_id = models.IntegerField(
        max_length=255, blank=True, null=True, db_index=True
    )
    date = models.DateField(max_length=255, blank=True, null=True, db_index=True)
    val = models.FloatField(blank=True, null=True)
    detection_item = models.CharField(
        max_length=255, blank=True, null=True, db_index=True
    )
    model_no = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    tissue_type = models.CharField(max_length=255, blank=True, null=True, db_index=True)

    class Meta:
        db_table = "m_modeling_facs_growth_curve_data"
        ordering = ["model_id"]


class MModelEfficacyFacsGrowthCurveData(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_desc_info = models.ForeignKey(
        MModelDescInfo, on_delete=models.CASCADE, db_column="model_uuid", db_index=True
    )
    model_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    group_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    animal_id = models.IntegerField(
        max_length=255, blank=True, null=True, db_index=True
    )
    date = models.DateField(max_length=255, blank=True, null=True, db_index=True)
    val = models.FloatField(blank=True, null=True)
    detection_item = models.CharField(
        max_length=255, blank=True, null=True, db_index=True
    )
    efficacy_num = models.CharField(
        max_length=255, blank=True, null=True, db_index=True
    )
    tissue_type = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    days = models.IntegerField(db_index=True, null=True, blank=True)

    class Meta:
        db_table = "m_model_efficacy_facs_growth_curve_data"
        ordering = ["model_id", "efficacy_num", "group_id", "date"]


class OSStats(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    model_desc_info = models.ForeignKey(
        MModelDescInfo, on_delete=models.CASCADE, db_column="model_uuid", db_index=True
    )
    model_nos = models.JSONField(default=list, db_index=True)
    groups = models.JSONField(default=None, null=True, db_index=True)
    img = models.CharField(max_length=255, null=True, blank=True)
    p_value = models.FloatField(default=None, null=True)
    groups_p_value = models.FloatField(default=None, null=True)
    hr = models.FloatField(default=None, null=True)
    ci_95_lower = models.FloatField(default=None, null=True)
    ci_95_upper = models.FloatField(default=None, null=True)
    type = models.CharField(max_length=16, db_index=True)

    class Meta:
        db_table = "os_stats"
        ordering = ["model_desc_info", "type"]


class FACSStats(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    model_desc_info = models.ForeignKey(
        MModelDescInfo, on_delete=models.CASCADE, db_column="model_uuid", db_index=True
    )
    panel = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    model_no = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    group_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    detection_item = models.CharField(
        max_length=255, null=True, blank=True, db_index=True
    )
    date = models.DateField(null=True, blank=True, db_index=True)
    days = models.IntegerField(null=True, blank=True, db_index=True)
    tissue_type = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    avg = models.FloatField(null=True, blank=True, db_index=True)
    max = models.FloatField(null=True, blank=True, db_index=True)
    min = models.FloatField(null=True, blank=True, db_index=True)
    type = models.CharField(max_length=16, db_index=True)
    drug_name = models.CharField(
        max_length=255, db_index=True, null=True, blank=True, default=""
    )
    is_tumor = models.BooleanField(blank=True, null=True, db_index=True)

    class Meta:
        db_table = "facs_stats"
        ordering = ["model_desc_info", "model_no", "date", "group_id", "type"]


class ELISAStats(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    model_desc_info = models.ForeignKey(
        MModelDescInfo, on_delete=models.CASCADE, db_column="model_uuid", db_index=True
    )
    panel = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    model_no = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    group_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    detection_item = models.CharField(
        max_length=255, null=True, blank=True, db_index=True
    )
    date = models.DateField(null=True, blank=True, db_index=True)
    days = models.IntegerField(null=True, blank=True, db_index=True)
    tissue_type = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    avg = models.FloatField(null=True, blank=True, db_index=True)
    max = models.FloatField(null=True, blank=True, db_index=True)
    min = models.FloatField(null=True, blank=True, db_index=True)
    type = models.CharField(max_length=16, db_index=True)
    drug_name = models.CharField(
        max_length=100, db_index=True, null=True, blank=True, default=""
    )
    is_tumor = models.BooleanField(blank=True, null=True, db_index=True)

    class Meta:
        db_table = "elisa_stats"
        ordering = ["model_desc_info", "model_no", "date", "group_id", "type"]


class HEImg(models.Model):
    id = models.BigAutoField(primary_key=True)
    photo_id = models.CharField(max_length=255)
    model_desc_info = models.ForeignKey(
        MModelDescInfo, on_delete=models.CASCADE, db_column="model_uuid", db_index=True
    )
    model_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    passage = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    ffpe_id = models.CharField(max_length=255, blank=True, null=True)
    path = models.CharField(max_length=255, blank=True, null=True)
    for_bd = models.BooleanField(blank=True, null=True, default=True, db_index=True)

    class Meta:
        db_table = "he_img"
        ordering = ["model_desc_info", "passage"]


class TWStats(models.Model):
    id = models.BigAutoField(primary_key=True)
    model_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    model_desc_info = models.ForeignKey(
        MModelDescInfo, on_delete=models.CASCADE, db_column="model_uuid", db_index=True
    )
    model_no = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    group_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    date = models.DateField(null=True, blank=True, db_index=True)
    days = models.IntegerField(null=True, blank=True, db_index=True)
    avg = models.FloatField(null=True, blank=True, db_index=True)
    max = models.FloatField(null=True, blank=True, db_index=True)
    min = models.FloatField(null=True, blank=True, db_index=True)
    type = models.CharField(max_length=16, db_index=True)
    drug_name = models.CharField(
        max_length=100, db_index=True, null=True, blank=True, default=""
    )

    class Meta:
        db_table = "tw_stats"
        ordering = ["model_desc_info", "type", "model_no", "date", "group_id"]


class OncoKB(models.Model):
    gene = models.CharField(
        "Gene", max_length=100, null=True, blank=True, db_index=True
    )
    mutant = models.CharField(
        "Mutant", max_length=100, null=True, blank=True, db_index=True
    )
    oncogenic = models.CharField(
        "Oncogenic", max_length=100, null=True, blank=True, db_index=True
    )
    mutation_effect = models.CharField(
        "Mutation Effect", max_length=100, null=True, blank=True, db_index=True
    )
    level = models.CharField(
        "Level", max_length=100, null=True, blank=True, db_index=True
    )
    alterations = models.JSONField("Alterations", null=True, blank=True)
    level_associated_cancer_types = models.CharField(
        "Level-associated cancer types", max_length=256, null=True, blank=True
    )
    drugs = models.JSONField("Drugs", null=True, blank=True)
    citations = models.IntegerField("Citations", blank=True, null=True, db_index=True)
    mutation_description = models.TextField(
        "Mutation Description", blank=True, null=True
    )
    drug_description = models.TextField("Drug Description", blank=True, null=True)

    class Meta:
        db_table = "oncokb"
        ordering = ["gene", "mutant"]
