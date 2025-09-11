// Mapping of Home Assistant domains / device classes to icons.
// Each entry provides an MDI name (for Home Assistant) and a simple emoji fallback
// used by the React admin UI. This keeps the UI lightweight while conveying
// semantic icons; tooltips show the suggested `mdi:` name.

const icons: { [key: string]: { mdi: string; emoji: string } } = {
  // explicit items requested
  script: { mdi: 'script', emoji: '📜' },
  person: { mdi: 'account', emoji: '👤' },
  update: { mdi: 'update', emoji: '🔄' },
  conversation: { mdi: 'chat', emoji: '💬' },
  todo: { mdi: 'format-list-checkbox', emoji: '🗒️' },

  // common domains
  light: { mdi: 'lightbulb', emoji: '💡' },
  switch: { mdi: 'power-plug', emoji: '🔌' },
  sensor: { mdi: 'gauge', emoji: '📈' },
  climate: { mdi: 'thermostat', emoji: '🌡️' },
  binary_sensor: { mdi: 'door', emoji: '🔔' },
  lock: { mdi: 'lock', emoji: '🔒' },
  camera: { mdi: 'camera', emoji: '📷' },
  cover: { mdi: 'garage', emoji: '🪟' },
  fan: { mdi: 'fan', emoji: '🌀' },
  media_player: { mdi: 'cast', emoji: '▶️' },
  vacuum: { mdi: 'robot-vacuum', emoji: '🤖' },
  scene: { mdi: 'palette', emoji: '🎛️' },
  automation: { mdi: 'robot', emoji: '🤖' },
  input_boolean: { mdi: 'toggle-switch', emoji: '🔛' },
  input_select: { mdi: 'format-list-bulleted', emoji: '▾' },
  calendar: { mdi: 'calendar', emoji: '📅' },

  // sensor types
  temperature: { mdi: 'thermometer', emoji: '🌡️' },
  humidity: { mdi: 'water-percent', emoji: '💧' },
  battery: { mdi: 'battery', emoji: '🔋' },
  power: { mdi: 'flash', emoji: '⚡' },
  co2: { mdi: 'molecule', emoji: '🧪' },
}

export function getIconForEntity(entity_id: string, device_class?: string | null) {
  // domain is prefix before first dot
  const domain = entity_id.split('.')[0]

  // prefer explicit device_class mappings for sensors
  if (domain === 'sensor' && device_class) {
    const dc = device_class.toLowerCase()
    if (icons[dc]) return icons[dc]
    // common substrings
    if (dc.includes('temperature')) return icons.temperature
    if (dc.includes('humidity')) return icons.humidity
    if (dc.includes('battery')) return icons.battery
    if (dc.includes('power') || dc.includes('energy') || dc.includes('watt')) return icons.power
  }

  if (icons[domain]) return icons[domain]

  // heuristics by entity_id
  if (entity_id.includes('temp') || entity_id.includes('temperature')) return icons.temperature
  if (entity_id.includes('humid') || entity_id.includes('vocht')) return icons.humidity
  if (entity_id.includes('battery') || entity_id.includes('batt')) return icons.battery
  if (entity_id.includes('power') || entity_id.includes('watt') || entity_id.includes('kwh')) return icons.power

  // fallback
  return { mdi: 'device-unknown', emoji: '🔧' }
}

export default icons
