// Search reference models only. Approved supplier listings have a separate API.
export function reviewedAliases(reviews) {
  const aliases = new Map();
  for (const [id, review] of Object.entries(reviews || {})) {
    if (review?.status === 'approved' && typeof review.modelName === 'string') {
      aliases.set(id, review.modelName);
    }
  }
  return aliases;
}

export function energyTokens(value) {
  return String(value || '').split(/[,/]/).map(part=>part.trim()).filter(Boolean);
}

export function filterReferenceModels(models, filters, aliases = new Map()) {
  const keyword = String(filters.keyword || '').trim().toLocaleLowerCase();
  return models.filter(model => {
    if (filters.brand && model.brand !== filters.brand) return false;
    if (filters.bodyType && model.bodyType !== filters.bodyType) return false;
    if (filters.energy && !energyTokens(model.energy).includes(filters.energy)) return false;
    if (filters.year && String(model.year ?? '') !== String(filters.year)) return false;
    if (!keyword) return true;
    return [model.brand, model.model, aliases.get(model.id)]
      .filter(Boolean).join(' ').toLocaleLowerCase().includes(keyword);
  });
}
