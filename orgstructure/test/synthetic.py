"""Reproducible control kit: edition 9 with a deleted and a copied duty."""
from pathlib import Path
from app.parser import parse


def make_synthetic():
    path=next(Path('data').glob('*9*.txt'))
    original=path.read_text()
    doc=parse('before.txt',original.encode())
    deleted=next(p for p in doc.paragraphs if p['clause']=='5.5.6')
    copied=next(p for p in doc.paragraphs if p['clause']=='5.4.5')
    modified=original.replace(deleted['quote'],'',1)
    modified=modified.replace('5.6. Директоры', '5.5.11. '+copied['text']+'\n5.6. Директоры',1)
    return original,modified,deleted,copied

if __name__=='__main__':
    import argparse
    cli=argparse.ArgumentParser();cli.add_argument('--output',required=True)
    output=Path(cli.parse_args().output);output.mkdir(parents=True,exist_ok=True)
    old,new,_,_=make_synthetic()
    (output/'before.txt').write_text(old)
    (output/'after.txt').write_text(new)
    print('Созданы before.txt и after.txt:',output)
