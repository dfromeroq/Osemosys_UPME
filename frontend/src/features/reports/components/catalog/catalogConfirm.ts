/** Confirmación reforzada para registros de sistema en el catálogo admin. */

export function confirmCatalogMutation(opts: {
  isSystem?: boolean;
  action: 'edit' | 'delete';
  entityLabel: string;
}): boolean {
  const verb = opts.action === 'delete' ? 'eliminar' : 'editar';
  if (opts.isSystem) {
    return window.confirm(
      `«${opts.entityLabel}» es un registro de sistema.\n\n¿Confirmas que deseas ${verb}lo? Esta acción puede afectar gráficas en producción.`,
    );
  }
  if (opts.action === 'delete') {
    return window.confirm(`¿Eliminar «${opts.entityLabel}»?`);
  }
  return true;
}
