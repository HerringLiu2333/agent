import tree_sitter_c as tsc
from tree_sitter import Language, Parser

C_LANGUAGE = Language(tsc.language())
parser = Parser(C_LANGUAGE)
print("C language:", C_LANGUAGE)