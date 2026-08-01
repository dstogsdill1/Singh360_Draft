export interface PdfReplacementMappingItem {
  existingPageId: string;
  pageIndex: number;
}

/**
 * The replace API accepts only the revised pages named by the explicit stable
 * page mapping. Extra selected preview pages remain available for the user to
 * import through Add as New Pages, but must not make a partial replacement
 * fail validation.
 */
export function pdfImportRequestSelection(
  action: 'add' | 'replace',
  selectedPages: number[],
  mapping?: PdfReplacementMappingItem[],
): number[] {
  if (action === 'add') return [...selectedPages];
  return (mapping ?? []).map((item) => item.pageIndex);
}
