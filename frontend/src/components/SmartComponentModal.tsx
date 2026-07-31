import { useState } from 'react';
import type {
  SmartBankLayout,
  SmartComponentConfig,
} from '../model/types';
import {
  normalizeSmartComponentConfig,
  parseSmartContactorCustomLabels,
  SMART_COMPONENT_CHOICES,
  SMART_COMPONENT_LABELS,
} from '../model/smartComponents';

interface Props {
  initialConfig: SmartComponentConfig;
  mode: 'insert' | 'edit';
  onApply: (config: SmartComponentConfig) => void;
  onCancel: () => void;
}

const TERMINAL_BANK_OPTIONS = 'ABCDEFGHIJKL'.split('');

export default function SmartComponentModal({
  initialConfig,
  mode,
  onApply,
  onCancel,
}: Props) {
  const [config, setConfig] = useState<SmartComponentConfig>(
    () => normalizeSmartComponentConfig(initialConfig, initialConfig.kind),
  );
  const [contactorCustomLabelsText, setContactorCustomLabelsText] = useState(
    () => initialConfig.kind === 'contactor-bank'
      ? initialConfig.customLabels.join('\n')
      : '',
  );
  const choice = SMART_COMPONENT_CHOICES.find((item) => item.kind === config.kind);

  const patch = (values: Record<string, unknown>) => {
    setConfig((current) => normalizeSmartComponentConfig(
      { ...current, ...values },
      current.kind,
    ));
  };

  const bankLayoutFields = (
    layout: SmartBankLayout,
    gridColumns: number,
    spacing: number,
  ) => (
    <>
      <label>
        Layout
        <select
          aria-label="Bank layout"
          value={layout}
          onChange={(event) => patch({ layout: event.target.value })}
        >
          <option value="horizontal">Horizontal</option>
          <option value="vertical">Vertical</option>
          <option value="grid">Grid</option>
        </select>
      </label>
      {layout === 'grid' ? (
        <label>
          Grid columns
          <input
            aria-label="Grid columns"
            type="number"
            min={1}
            max={10}
            value={gridColumns}
            onChange={(event) => patch({ gridColumns: Number(event.target.value) })}
          />
        </label>
      ) : null}
      <label>
        Spacing
        <input
          aria-label="Bank spacing"
          type="number"
          min={0}
          max={100}
          value={spacing}
          onChange={(event) => patch({ spacing: Number(event.target.value) })}
        />
      </label>
    </>
  );

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <form
        className="modal smart-component-modal"
        aria-label={`${mode === 'edit' ? 'Edit' : 'Insert'} ${SMART_COMPONENT_LABELS[config.kind]}`}
        onClick={(event) => event.stopPropagation()}
        onSubmit={(event) => {
          event.preventDefault();
          const next = config.kind === 'contactor-bank'
            ? {
              ...config,
              customLabels: parseSmartContactorCustomLabels(contactorCustomLabelsText),
            }
            : config;
          onApply(normalizeSmartComponentConfig(next, next.kind));
        }}
      >
        <div className="modal-head">
          <div>
            <h2>{mode === 'edit' ? 'Edit' : 'Insert'} {SMART_COMPONENT_LABELS[config.kind]}</h2>
            <p>{choice?.description}</p>
          </div>
          <button type="button" className="modal-x" aria-label="Close smart component editor" onClick={onCancel}>×</button>
        </div>
        <div className="modal-body smart-component-form">
          {config.kind === 'panel-enclosure' ? (
            <>
              <fieldset>
                <legend>Panel identity</legend>
                <div className="smart-component-grid">
                  <label>
                    Panel type
                    <select
                      aria-label="Panel type"
                      value={config.panelType}
                      onChange={(event) => patch({ panelType: event.target.value })}
                    >
                      {['WICP', 'LCP', 'PCP', 'CCP', 'REMS', 'CUSTOM'].map((value) => (
                        <option key={value} value={value}>{value === 'CUSTOM' ? 'Custom' : value}</option>
                      ))}
                    </select>
                  </label>
                  {config.panelType === 'CUSTOM' ? (
                    <label>
                      Custom panel type
                      <input
                        aria-label="Custom panel type"
                        value={config.customPanelType}
                        onChange={(event) => patch({ customPanelType: event.target.value })}
                      />
                    </label>
                  ) : null}
                  <label>
                    Editable title
                    <input
                      aria-label="Panel title"
                      value={config.title}
                      onChange={(event) => patch({ title: event.target.value })}
                    />
                  </label>
                  <label className="smart-component-span">
                    Header
                    <input
                      aria-label="Panel header"
                      value={config.header}
                      onChange={(event) => patch({ header: event.target.value })}
                    />
                  </label>
                </div>
              </fieldset>
              <fieldset>
                <legend>Size and device grid</legend>
                <div className="smart-component-grid">
                  <label>
                    Width
                    <input
                      aria-label="Panel width"
                      type="number"
                      min={260}
                      max={1200}
                      value={config.width}
                      onChange={(event) => patch({ width: Number(event.target.value) })}
                    />
                  </label>
                  <label>
                    Height
                    <input
                      aria-label="Panel height"
                      type="number"
                      min={220}
                      max={720}
                      value={config.height}
                      onChange={(event) => patch({ height: Number(event.target.value) })}
                    />
                  </label>
                  <label>
                    Device rows
                    <input
                      aria-label="Device grid rows"
                      type="number"
                      min={1}
                      max={12}
                      value={config.deviceRows}
                      onChange={(event) => patch({ deviceRows: Number(event.target.value) })}
                    />
                  </label>
                  <label>
                    Device columns
                    <input
                      aria-label="Device grid columns"
                      type="number"
                      min={1}
                      max={12}
                      value={config.deviceColumns}
                      onChange={(event) => patch({ deviceColumns: Number(event.target.value) })}
                    />
                  </label>
                  <label className="smart-component-span">
                    Device labels — one line per grid cell
                    <textarea
                      aria-label="Device grid labels"
                      rows={8}
                      value={config.deviceLabels.join('\n')}
                      onChange={(event) => patch({ deviceLabels: event.target.value.split(/\r?\n/) })}
                    />
                  </label>
                </div>
              </fieldset>
            </>
          ) : null}

          {config.kind === 'contactor-bank' ? (
            <>
              <fieldset>
                <legend>Contactor numbering</legend>
                <div className="smart-component-grid">
                  <label>
                    Prefix
                    <input
                      aria-label="Contactor prefix"
                      value={config.prefix}
                      onChange={(event) => patch({ prefix: event.target.value })}
                    />
                  </label>
                  <label>
                    Start number
                    <input
                      aria-label="Contactor start number"
                      type="number"
                      min={0}
                      max={999}
                      value={config.startNumber}
                      onChange={(event) => patch({ startNumber: Number(event.target.value) })}
                    />
                  </label>
                  <label>
                    Numbered contactors count
                    <input
                      aria-label="Numbered contactors count"
                      type="number"
                      min={0}
                      max={20}
                      value={config.numberedCount}
                      onChange={(event) => patch({ numberedCount: Number(event.target.value) })}
                    />
                  </label>
                  <label>
                    Spare contactors count
                    <input
                      aria-label="Spare contactors count"
                      type="number"
                      min={0}
                      max={Math.max(0, 20 - config.numberedCount)}
                      value={config.spareCount}
                      onChange={(event) => patch({ spareCount: Number(event.target.value) })}
                    />
                  </label>
                  <label>
                    Spare label
                    <input
                      aria-label="Spare contactor label"
                      value={config.spareLabel}
                      onChange={(event) => patch({ spareLabel: event.target.value })}
                    />
                  </label>
                  <label>
                    Total quantity
                    <input
                      aria-label="Total contactor quantity"
                      value={
                        parseSmartContactorCustomLabels(contactorCustomLabelsText).length
                        || config.numberedCount + config.spareCount
                      }
                      readOnly
                    />
                  </label>
                  <label className="smart-component-check">
                    <input
                      aria-label="Auto-number contactors"
                      type="checkbox"
                      checked={config.autoNumber}
                      onChange={(event) => patch({ autoNumber: event.target.checked })}
                    />
                    Auto-number
                  </label>
                  <label className="smart-component-span">
                    Optional custom labels — one per contactor
                    <textarea
                      aria-label="Custom contactor labels"
                      rows={7}
                      value={contactorCustomLabelsText}
                      onChange={(event) => setContactorCustomLabelsText(event.target.value)}
                      placeholder={'C1\nC1\nC2\nSPARE\nSPARE'}
                    />
                  </label>
                </div>
                <p className="smart-component-note">
                  Leave custom labels empty to generate numbered contactors followed by spares. A custom list replaces generated labels and preserves order and duplicates.
                </p>
              </fieldset>
              <fieldset>
                <legend>Poles and layout</legend>
                <div className="smart-component-grid">
                  <label>
                    Physical poles
                    <select
                      aria-label="Physical poles"
                      value={config.physicalPoles}
                      onChange={(event) => patch({ physicalPoles: event.target.value })}
                    >
                      <option value="1P">1P</option>
                      <option value="2P">2P</option>
                      <option value="3P">3P</option>
                    </select>
                  </label>
                  <label>
                    Scheduled-poles text
                    <input
                      aria-label="Scheduled poles"
                      value={config.scheduledPoles}
                      onChange={(event) => patch({ scheduledPoles: event.target.value })}
                    />
                  </label>
                  {bankLayoutFields(config.layout, config.gridColumns, config.spacing)}
                </div>
              </fieldset>
              <p className="smart-component-note">
                Inserted as one editable group. Use Edit Smart Component to regenerate it, or Explode to edit individual contactors and text.
              </p>
            </>
          ) : null}

          {config.kind === 'relay-bank' ? (
            <fieldset>
              <legend>Relay numbering and layout</legend>
              <div className="smart-component-grid">
                <label>
                  Prefix
                  <input
                    aria-label="Relay prefix"
                    value={config.prefix}
                    onChange={(event) => patch({ prefix: event.target.value })}
                  />
                </label>
                <label>
                  Start number
                  <input
                    aria-label="Relay start number"
                    type="number"
                    min={0}
                    max={999}
                    value={config.startNumber}
                    onChange={(event) => patch({ startNumber: Number(event.target.value) })}
                  />
                </label>
                <label>
                  Quantity
                  <input
                    aria-label="Relay quantity"
                    type="number"
                    min={1}
                    max={20}
                    value={config.quantity}
                    onChange={(event) => patch({ quantity: Number(event.target.value) })}
                  />
                </label>
                <label className="smart-component-check">
                  <input
                    aria-label="Auto-number relays"
                    type="checkbox"
                    checked={config.autoNumber}
                    onChange={(event) => patch({ autoNumber: event.target.checked })}
                  />
                  Auto-number
                </label>
                {bankLayoutFields(config.layout, config.gridColumns, config.spacing)}
              </div>
            </fieldset>
          ) : null}

          {config.kind === 'power-monitor-pack' ? (
            <fieldset>
              <legend>Power monitor pack</legend>
              <div className="smart-component-grid">
                <label>
                  Model
                  <select
                    aria-label="Power monitor model"
                    value={config.model}
                    onChange={(event) => patch({ model: event.target.value })}
                  >
                    {['PS48', 'PS24', 'PS12', 'PS3'].map((value) => (
                      <option key={value} value={value}>{value}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Mount
                  <select
                    aria-label="Power monitor mount"
                    value={config.mount}
                    onChange={(event) => patch({ mount: event.target.value })}
                  >
                    <option value="WALL">Wall</option>
                    <option value="DIN">DIN</option>
                  </select>
                </label>
                <label>
                  Terminal bank
                  <select
                    aria-label="Power monitor terminal bank"
                    value={config.terminalBank}
                    onChange={(event) => patch({ terminalBank: event.target.value })}
                  >
                    {TERMINAL_BANK_OPTIONS.map((value) => (
                      <option key={value} value={value}>{value}</option>
                    ))}
                    <option value="CUSTOM">Custom</option>
                  </select>
                </label>
                {config.terminalBank === 'CUSTOM' ? (
                  <label>
                    Custom terminal bank
                    <input
                      aria-label="Custom terminal bank"
                      value={config.customTerminalBank}
                      onChange={(event) => patch({ customTerminalBank: event.target.value })}
                    />
                  </label>
                ) : null}
                <label>
                  CT quantity
                  <input
                    aria-label="CT quantity"
                    type="number"
                    min={0}
                    max={48}
                    value={config.ctQuantity}
                    onChange={(event) => patch({ ctQuantity: Number(event.target.value) })}
                  />
                </label>
                <label>
                  CT type
                  <select
                    aria-label="CT type"
                    value={config.ctType}
                    onChange={(event) => patch({ ctType: event.target.value })}
                  >
                    {['Split-core', 'Solid-core', 'Rogowski', 'Custom'].map((value) => (
                      <option key={value} value={value}>{value}</option>
                    ))}
                  </select>
                </label>
                {config.ctType === 'Custom' ? (
                  <label className="smart-component-span">
                    Custom CT type
                    <input
                      aria-label="Custom CT type"
                      value={config.customCtType}
                      onChange={(event) => patch({ customCtType: event.target.value })}
                    />
                  </label>
                ) : null}
              </div>
            </fieldset>
          ) : null}

          {config.kind === 'terminal-bank' ? (
            <fieldset>
              <legend>Terminal bank</legend>
              <div className="smart-component-grid">
                <label className="smart-component-span">
                  Bank label
                  <input
                    aria-label="Terminal bank label"
                    value={config.label}
                    onChange={(event) => patch({ label: event.target.value })}
                  />
                </label>
                <label>
                  Terminal prefix
                  <input
                    aria-label="Terminal prefix"
                    value={config.prefix}
                    onChange={(event) => patch({ prefix: event.target.value })}
                  />
                </label>
                <label>
                  Start number
                  <input
                    aria-label="Terminal start number"
                    type="number"
                    min={0}
                    max={999}
                    value={config.startNumber}
                    onChange={(event) => patch({ startNumber: Number(event.target.value) })}
                  />
                </label>
                <label>
                  Quantity
                  <input
                    aria-label="Terminal quantity"
                    type="number"
                    min={1}
                    max={48}
                    value={config.quantity}
                    onChange={(event) => patch({ quantity: Number(event.target.value) })}
                  />
                </label>
                <label>
                  Layout
                  <select
                    aria-label="Terminal bank layout"
                    value={config.layout}
                    onChange={(event) => patch({ layout: event.target.value })}
                  >
                    <option value="horizontal">Horizontal</option>
                    <option value="vertical">Vertical</option>
                  </select>
                </label>
                <label>
                  Spacing
                  <input
                    aria-label="Terminal spacing"
                    type="number"
                    min={0}
                    max={40}
                    value={config.spacing}
                    onChange={(event) => patch({ spacing: Number(event.target.value) })}
                  />
                </label>
              </div>
            </fieldset>
          ) : null}

          {config.kind === 'labeled-device' ? (
            <fieldset>
              <legend>Generic labeled device</legend>
              <div className="smart-component-grid">
                <label className="smart-component-span">
                  Device label
                  <input
                    aria-label="Device label"
                    value={config.label}
                    onChange={(event) => patch({ label: event.target.value })}
                  />
                </label>
                <label className="smart-component-span">
                  Secondary label
                  <input
                    aria-label="Device secondary label"
                    value={config.secondaryLabel}
                    onChange={(event) => patch({ secondaryLabel: event.target.value })}
                  />
                </label>
                <label>
                  Width
                  <input
                    aria-label="Device width"
                    type="number"
                    min={80}
                    max={600}
                    value={config.width}
                    onChange={(event) => patch({ width: Number(event.target.value) })}
                  />
                </label>
                <label>
                  Height
                  <input
                    aria-label="Device height"
                    type="number"
                    min={60}
                    max={400}
                    value={config.height}
                    onChange={(event) => patch({ height: Number(event.target.value) })}
                  />
                </label>
                <label>
                  Terminals
                  <input
                    aria-label="Device terminal count"
                    type="number"
                    min={0}
                    max={12}
                    value={config.terminalCount}
                    onChange={(event) => patch({ terminalCount: Number(event.target.value) })}
                  />
                </label>
              </div>
            </fieldset>
          ) : null}
        </div>
        <div className="modal-foot">
          <button type="button" className="btn" onClick={onCancel}>Cancel</button>
          <button type="submit" className="btn btn-primary">
            {mode === 'edit' ? 'Apply Smart Component Changes' : `Insert ${SMART_COMPONENT_LABELS[config.kind]}`}
          </button>
        </div>
      </form>
    </div>
  );
}
