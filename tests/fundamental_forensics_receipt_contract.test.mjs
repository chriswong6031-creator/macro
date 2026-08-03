import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../templates/fundamental_forensics.js', import.meta.url), 'utf8');
const windowObject = {
  location: { hostname: 'contract.test' },
  matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
  __FF_RECEIPT_CONTRACT_TEST__: true,
};
const context = vm.createContext({
  window: windowObject,
  document: { readyState: 'loading', addEventListener() {} },
  console,
  URL,
  URLSearchParams,
});
vm.runInContext(source, context, { filename: 'fundamental_forensics.js' });
const contract = windowObject.__FF_RECEIPT_CONTRACT_TEST__;

const hex = (character) => character.repeat(64);
const snapshotId = `ffqsv2_${hex('a')}`;
const baseSnapshotId = `ffqs_${hex('b')}`;
const rootId = (character) => `metric_cell_${hex(character)}`;
const occurrenceId = (character) => `rawfact_${hex(character)}`;
const at = '2026-08-02T00:00:00.000000Z';
const publishedAt = '2026-08-02T00:05:00.000000Z';

const authority = () => ({
  positive_claim: 'B3_selected_member_companyfacts_row_correspondence_only',
  coverage_scope: 'selected_raw_fact_leaves_only',
  claim_basis: 'sealed_publication_receipt',
  source_reverified_at_read: false,
  match_body_replayed_at_read: false,
  nonclaims: {
    filing_complete: false,
    trading_authority: false,
    neural_web_authority: false,
    accounting_correctness: false,
  },
});

const latest = () => ({
  snapshot_id: snapshotId,
  base_snapshot_id: baseSnapshotId,
  query_hash: hex('c'),
  published_at: publishedAt,
  policy: {
    version: 'ffqsv2_exact_join/v1',
    fingerprint: '6e4ba04cf9c775ac280ba1426985246ffbdf730222b4521c4b26a41f5623871a',
  },
  clocks: {
    query_source_snapshot_at: at,
    query_recorded_at: at,
    query_computed_at: '2026-08-02T00:01:00.000000Z',
    query_published_at: '2026-08-02T00:02:00.000000Z',
    operator_verification_observed_at: '2026-08-02T00:03:00.000000Z',
    published_at: publishedAt,
  },
  coverage_summary: {
    coverage_scope: 'selected_raw_fact_leaves_only',
    positive_label: 'B3_selected_member_companyfacts_row_correspondence_only',
    root_cell_count: 4,
    all_leaves_attested: 1,
    partially_attested: 1,
    not_attested: 1,
    not_evaluable: 1,
  },
  companyfacts_conversion_receipt: {
    receipt_id: `cffledger_${hex('d')}`,
    schema: 'fundamental_forensics.companyfacts_ledger_receipt/v2',
    adapter_version: '2.0.0',
    capture_id: `ffseccfc_${hex('e')}`,
    manifest_id: `ffseccfm_${hex('f')}`,
    cik: '0000320193',
    clocks: {
      acquisition_started_at: at,
      captured_at: at,
      recorded_at: at,
      source_snapshot_at: at,
      submissions_recorded_at: at,
    },
    availability: 'available',
    occurrence_count: 4,
    output_occurrence_count: 4,
    pit_eligible_count: 3,
  },
  authority: authority(),
});

const root = (id, selected, eligible, attested, status) => ({
  root_cell_id: id,
  selected_leaf_occurrence_ids: selected,
  eligible_leaf_occurrence_ids: eligible,
  attested_occurrence_ids: attested,
  status,
});

const roots = () => [
  root(rootId('1'), [occurrenceId('1')], [occurrenceId('1')], [occurrenceId('1')], 'all_leaves_attested'),
  root(rootId('2'), [occurrenceId('2')], [occurrenceId('2')], [], 'not_attested'),
  root(
    rootId('3'),
    [occurrenceId('3'), occurrenceId('4')],
    [occurrenceId('3'), occurrenceId('4')],
    [occurrenceId('3')],
    'partially_attested',
  ),
  root(rootId('4'), [occurrenceId('5')], [], [], 'not_evaluable'),
];

const clone = (value) => JSON.parse(JSON.stringify(value));

const page = (receipt = latest(), rows = roots()) => ({
  snapshot_id: receipt.snapshot_id,
  base_snapshot_id: receipt.base_snapshot_id,
  query_hash: receipt.query_hash,
  published_at: receipt.published_at,
  authority: clone(receipt.authority),
  page: { cursor: null, next_cursor: null, limit: 25, returned: rows.length, total: rows.length },
  roots: rows,
});

const detail = (receipt = latest()) => ({
  snapshot_id: receipt.snapshot_id,
  base_snapshot_id: receipt.base_snapshot_id,
  query_hash: receipt.query_hash,
  published_at: receipt.published_at,
  authority: clone(receipt.authority),
  root: roots()[2],
  waterfall: [
    {
      occurrence_id: occurrenceId('3'),
      eligible: true,
      attested: true,
      attestation_id: `ffatt_${hex('5')}`,
      match_id: `ffatt_match_${hex('6')}`,
      companyfacts: {
        cik: '0000320193',
        accession: '0000320193-26-000001',
        taxonomy: 'us-gaap',
        concept: 'RevenueFromContractWithCustomerExcludingAssessedTax',
        unit: 'USD',
        period: { start: '2025-10-01', end: '2025-12-31' },
        value: '124300000000',
      },
      stored_b3_projection: {
        attestation_id: `ffatt_${hex('5')}`,
        authority_snapshot_id: `ffsecsrc_${hex('7')}`,
        package_id: `ffpkg_${hex('8')}`,
        extraction_id: `ffxbrl_${hex('9')}`,
        cik: '0000320193',
        accession: '0000320193-26-000001',
        companyfacts_capture_id: `ffseccfc_${hex('e')}`,
        companyfacts_manifest_id: `ffseccfm_${hex('f')}`,
        companyfacts_response_sha256: hex('a'),
        companyfacts_match_count: 1,
        attested_at: at,
      },
    },
    { occurrence_id: occurrenceId('4'), eligible: true, attested: false },
  ],
});

test('strict CIK normalization refuses lossy issuer spoofing', () => {
  assert.equal(contract.normalizedCik('320193'), '0000320193');
  assert.equal(contract.normalizedCik('0000320193'), '0000320193');
  assert.equal(contract.normalizedCik('evil0000320193'), '');
  assert.equal(contract.normalizedCik('00000320193'), '');
});

test('latest receipt validates the fixed identity, authority, clocks, and counts', () => {
  assert.ok(contract.validatedLatestReceipt(latest()));
  const mutations = [
    (value) => { value.companyfacts_conversion_receipt.cik = 'evil0000320193'; },
    (value) => { value.policy.version = 'future-unreviewed'; },
    (value) => { value.clocks.query_computed_at = '2026-08-02T00:06:00.000000Z'; },
    (value) => { value.clocks.query_source_snapshot_at = '2026-02-30T00:00:00.000000Z'; },
    (value) => { value.clocks.query_source_snapshot_at = '0000-01-01T00:00:00.000000Z'; },
    (value) => {
      value.clocks.query_computed_at = '2026-08-02T00:01:00.000999Z';
      value.clocks.query_published_at = '2026-08-02T00:01:00.000001Z';
    },
    (value) => { value.authority.nonclaims.trading_authority = true; },
    (value) => { value.coverage_summary.root_cell_count = 5; },
    (value) => { value.companyfacts_conversion_receipt.pit_eligible_count = 5; },
    (value) => { value.unreviewed_scope = true; },
  ];
  for (const mutate of mutations) {
    const hostile = latest();
    mutate(hostile);
    assert.equal(contract.validatedLatestReceipt(hostile), null);
  }
});

test('coverage roots enforce sorted unique membership and derived status', () => {
  for (const value of roots()) assert.ok(contract.validatedReceiptRoot(value));
  const badSubset = roots()[1];
  badSubset.attested_occurrence_ids = [occurrenceId('3')];
  assert.equal(contract.validatedReceiptRoot(badSubset), null);
  const badStatus = roots()[2];
  badStatus.status = 'all_leaves_attested';
  assert.equal(contract.validatedReceiptRoot(badStatus), null);
  const duplicate = roots()[0];
  duplicate.selected_leaf_occurrence_ids.push(occurrenceId('1'));
  assert.equal(contract.validatedReceiptRoot(duplicate), null);
});

test('root pages enforce identity, cursor, totals, ordering, and keyset continuity', () => {
  const receipt = latest();
  assert.ok(contract.validatedReceiptPagePayload(page(receipt), receipt, null, 0, null));
  for (const mutate of [
    (value) => { value.page.returned += 1; },
    (value) => { value.page.total += 1; },
    (value) => { value.page.limit = 100; },
    (value) => { value.roots.reverse(); },
    (value) => { value.snapshot_id = `ffqsv2_${hex('f')}`; },
  ]) {
    const hostile = page(receipt);
    mutate(hostile);
    assert.equal(contract.validatedReceiptPagePayload(hostile, receipt, null, 0, null), null);
  }

  const pagedReceipt = latest();
  pagedReceipt.coverage_summary = {
    ...pagedReceipt.coverage_summary,
    root_cell_count: 30,
    all_leaves_attested: 30,
    partially_attested: 0,
    not_attested: 0,
    not_evaluable: 0,
  };
  const allRows = Array.from({ length: 30 }, (_, index) => {
    const suffix = (index + 1).toString(16).padStart(64, '0');
    return root(
      `metric_cell_${suffix}`,
      [`rawfact_${suffix}`],
      [`rawfact_${suffix}`],
      [`rawfact_${suffix}`],
      'all_leaves_attested',
    );
  });
  const first = page(pagedReceipt, allRows.slice(0, 25));
  first.page.total = 30;
  first.page.next_cursor = first.roots.at(-1).root_cell_id;
  const firstValidated = contract.validatedReceiptPagePayload(first, pagedReceipt, null, 0, null);
  assert.ok(firstValidated);
  const second = page(pagedReceipt, allRows.slice(25));
  second.page.cursor = first.page.next_cursor;
  second.page.total = 30;
  assert.ok(contract.validatedReceiptPagePayload(second, pagedReceipt, first.page.next_cursor, 1, 30));
  first.page.next_cursor = rootId('f');
  assert.equal(contract.validatedReceiptPagePayload(first, pagedReceipt, null, 0, null), null);
});

test('detail waterfall must exactly bind the cached root and B3 projection', () => {
  const receipt = latest();
  const cached = contract.validatedReceiptPagePayload(page(receipt), receipt, null, 0, null).rows[2];
  assert.ok(contract.validatedReceiptDetailPayload(detail(receipt), receipt, rootId('3'), cached));
  for (const mutate of [
    (value) => { delete value.waterfall[0].companyfacts; },
    (value) => { value.waterfall[0].companyfacts.cik = '0000000001'; },
    (value) => { value.waterfall[0].stored_b3_projection.package_id = 'package-safe'; },
    (value) => { value.waterfall[0].stored_b3_projection.companyfacts_manifest_id = 'other'; },
    (value) => { value.waterfall[0].stored_b3_projection.attested_at = '2026-02-30T00:00:00.000000Z'; },
    (value) => { value.waterfall[0].companyfacts.period.end = '0000-01-01'; },
    (value) => { value.waterfall[0].companyfacts.value = 124300000000; },
    (value) => { value.waterfall.reverse(); },
    (value) => { value.waterfall[1].unexpected = true; },
  ]) {
    const hostile = detail(receipt);
    mutate(hostile);
    assert.equal(contract.validatedReceiptDetailPayload(hostile, receipt, rootId('3'), cached), null);
  }
  const drifted = clone(cached);
  drifted.status = 'not_attested';
  assert.equal(contract.validatedReceiptDetailPayload(detail(receipt), receipt, rootId('3'), drifted), null);

  const earlyCalendar = detail(receipt);
  earlyCalendar.waterfall[0].companyfacts.period = { start: '0001-01-01', end: '0001-12-31' };
  assert.ok(contract.validatedReceiptDetailPayload(earlyCalendar, receipt, rootId('3'), cached));

  const duplicatePair = detail(receipt);
  duplicatePair.root.attested_occurrence_ids.push(occurrenceId('4'));
  duplicatePair.root.status = 'all_leaves_attested';
  duplicatePair.waterfall[1] = clone(duplicatePair.waterfall[0]);
  duplicatePair.waterfall[1].occurrence_id = occurrenceId('4');
  const duplicateCached = contract.validatedReceiptRoot(duplicatePair.root);
  assert.ok(duplicateCached);
  assert.equal(
    contract.validatedReceiptDetailPayload(duplicatePair, receipt, rootId('3'), duplicateCached),
    null,
  );
});
