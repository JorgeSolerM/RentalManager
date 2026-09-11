"""Conservative conversion of address lines; PAIS is informational only."""


def address_line(row):
    clean=lambda key:' '.join((row.get(key) or '').split())
    street=clean('DIR')
    if not street:return None
    # Preserve the literal sigla: do not expand unknown or foreign road types.
    line=' '.join(x for x in (clean('DIRSIGLA'),street,clean('DIRNUM')) if x)
    for key,label in (('DIRPISO','planta'),('DIRLETRA','puerta')):
        if clean(key):line+=f', {label} {clean(key)}'
    return line
