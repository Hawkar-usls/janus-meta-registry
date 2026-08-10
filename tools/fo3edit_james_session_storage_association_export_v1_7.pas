unit fo3edit_james_session_storage_association_export_v1_7;

{
  JANUS / Fallout 3 — James session autopersistence / storage association exporter v1.7

  Read-only. Load exactly:
    Fallout3.esm
    Anchorage.esm
    ThePitt.esm
    BrokenSteel.esm
    PointLookout.esm
    Zeta.esm

  Purpose:
    Do not assume that a James payload requires a visible COPY/WRITE button.
    Instead audit whether James's exact Vault 112 session assets are connected to
    persistent storage, backend state, hidden/linked objects, or a transferable
    carrier class.

  Outputs:
    JANUS-James-Session-Seed-Leaves-v1.7.tsv
    JANUS-James-Session-Seed-Reverse-Refs-v1.7.tsv
    JANUS-James-Placed-Seed-Refs-v1.7.tsv
    JANUS-Vault112a-REFR-Inventory-v1.7.tsv
    JANUS-James-Storage-Candidates-v1.7.tsv

  No record is modified. Keyword or proximity hits are discovery evidence only.
}

var
  SeedLeafOut: TStringList;
  ReverseOut: TStringList;
  PlacedSeedOut: TStringList;
  Vault112RefOut: TStringList;
  CandidateOut: TStringList;
  LoadedOfficial: TStringList;
  UnexpectedPlugins: TStringList;
  SeenLogical: TStringList;
  SeenCandidateRecords: TStringList;
  StorageTerms: TStringList;
  Blocked: boolean;
  DuplicateLogicalCount: integer;

function CleanTSV(s: string): string;
begin
  s := StringReplace(s, #9, ' ', [rfReplaceAll]);
  s := StringReplace(s, #13, ' ', [rfReplaceAll]);
  s := StringReplace(s, #10, ' ', [rfReplaceAll]);
  Result := s;
end;

function Lower(s: string): string;
begin
  Result := LowerCase(s);
end;

function Hex8(v: cardinal): string;
begin
  Result := IntToHex(v, 8);
end;

function FloatInvariant(v: double): string;
begin
  Result := FloatToStr(v);
  Result := StringReplace(Result, ',', '.', [rfReplaceAll]);
end;

function BoolText(v: boolean): string;
begin
  if v then Result := 'true' else Result := 'false';
end;

function EndsWithText(s, suffix: string): boolean;
var
  n, m: integer;
begin
  n := Length(s);
  m := Length(suffix);
  if n < m then begin
    Result := false;
    exit;
  end;
  Result := CompareText(Copy(s, n - m + 1, m), suffix) = 0;
end;

function IsPluginFilename(fn: string): boolean;
begin
  Result := EndsWithText(fn, '.esm') or EndsWithText(fn, '.esp');
end;

function IsOfficialMaster(fn: string): boolean;
begin
  Result :=
    (CompareText(fn, 'Fallout3.esm') = 0) or
    (CompareText(fn, 'Anchorage.esm') = 0) or
    (CompareText(fn, 'ThePitt.esm') = 0) or
    (CompareText(fn, 'BrokenSteel.esm') = 0) or
    (CompareText(fn, 'PointLookout.esm') = 0) or
    (CompareText(fn, 'Zeta.esm') = 0);
end;

function IsJamesSeedFixed(id: cardinal): boolean;
begin
  Result :=
    (id = $00031190) or  { Vault112PodTermDad }
    (id = $00031191) or  { MQ04StressNoteDad }
    (id = $00031192) or  { MQ04StatusNoteDad }
    (id = $0004E79C) or  { MQ04Doc base }
    (id = $0006023C) or  { MQ04Doc placed ref }
    (id = $0005AE43) or  { MQ04DadPodScript }
    (id = $0004C255) or  { MQ04PlayerContainerScript }
    (id = $000254C9) or  { MQ04Script }
    (id = $0007DC71) or  { BettyScript }
    (id = $000C339E) or  { MQ04VersionControlCurrent }
    (id = $0004B1CF);    { MQ04PlayerPodScript control comparison }
end;

function JamesSeedLabel(id: cardinal): string;
begin
  Result := '';
  if id = $00031190 then Result := 'Vault112PodTermDad'
  else if id = $00031191 then Result := 'MQ04StressNoteDad'
  else if id = $00031192 then Result := 'MQ04StatusNoteDad'
  else if id = $0004E79C then Result := 'MQ04Doc'
  else if id = $0006023C then Result := 'MQ04DocRef'
  else if id = $0005AE43 then Result := 'MQ04DadPodScript'
  else if id = $0004C255 then Result := 'MQ04PlayerContainerScript'
  else if id = $000254C9 then Result := 'MQ04Script'
  else if id = $0007DC71 then Result := 'BettyScript'
  else if id = $000C339E then Result := 'MQ04VersionControlCurrent'
  else if id = $0004B1CF then Result := 'MQ04PlayerPodScript';
end;

function EffectiveWinning(e: IInterface): IInterface;
var
  root: IInterface;
begin
  Result := nil;
  if not Assigned(e) then exit;
  if ElementType(e) <> etMainRecord then exit;
  root := MasterOrSelf(e);
  if not Assigned(root) then root := e;
  Result := WinningOverride(root);
  if not Assigned(Result) then Result := root;
  if GetIsDeleted(Result) then Result := nil;
end;

function FirstNonEmpty(a, b, c: string): string;
begin
  Result := a;
  if Result = '' then Result := b;
  if Result = '' then Result := c;
end;

function SafePathValue(e: IInterface; path: string): string;
var
  x: IInterface;
begin
  Result := '';
  if not Assigned(e) then exit;
  x := ElementByPath(e, path);
  if Assigned(x) then Result := CleanTSV(GetEditValue(x));
end;

function CanonicalCellEditorID(e: IInterface): string;
var
  c, rootLoc: IInterface;
begin
  Result := '';
  c := GetContainer(e);
  while Assigned(c) do begin
    if (ElementType(c) = etMainRecord) and (Signature(c) = 'CELL') then begin
      rootLoc := MasterOrSelf(c);
      if not Assigned(rootLoc) then rootLoc := c;
      Result := CleanTSV(EditorID(rootLoc));
      exit;
    end;
    c := GetContainer(c);
  end;
end;

function CanonicalLocationKey(e: IInterface): string;
var
  c, rootLoc: IInterface;
  sig: string;
begin
  Result := '';
  c := GetContainer(e);
  while Assigned(c) do begin
    if ElementType(c) = etMainRecord then begin
      sig := Signature(c);
      if (sig = 'CELL') or (sig = 'WRLD') then begin
        rootLoc := MasterOrSelf(c);
        if not Assigned(rootLoc) then rootLoc := c;
        Result := sig + '|' + CleanTSV(GetFileName(GetFile(rootLoc))) + '|' + Hex8(GetLoadOrderFormID(rootLoc));
        exit;
      end;
    end;
    c := GetContainer(c);
  end;
end;

function FindStorageTerm(text: string): string;
var
  i: integer;
  t: string;
begin
  Result := '';
  t := Lower(text);
  for i := 0 to StorageTerms.Count - 1 do begin
    if Pos(StorageTerms[i], t) > 0 then begin
      Result := StorageTerms[i];
      exit;
    end;
  end;
end;

procedure AddStorageTerms;
begin
  StorageTerms.Add('memory');
  StorageTerms.Add('mem chip');
  StorageTerms.Add('memory chip');
  StorageTerms.Add('memchip');
  StorageTerms.Add('neural');
  StorageTerms.Add('engram');
  StorageTerms.Add('persist');
  StorageTerms.Add('archive');
  StorageTerms.Add('backup');
  StorageTerms.Add('snapshot');
  StorageTerms.Add('storage');
  StorageTerms.Add('store');
  StorageTerms.Add('save');
  StorageTerms.Add('restore');
  StorageTerms.Add('reload');
  StorageTerms.Add('cache');
  StorageTerms.Add('buffer');
  StorageTerms.Add('slot');
  StorageTerms.Add('sync');
  StorageTerms.Add('synchron');
  StorageTerms.Add('visiontron');
  StorageTerms.Add('think machine');
  StorageTerms.Add('lounger');
  StorageTerms.Add('resident');
  StorageTerms.Add('user unknown');
  StorageTerms.Add('transfer');
  StorageTerms.Add('serialize');
  StorageTerms.Add('copy');
  StorageTerms.Add('write');
end;

procedure EmitSeedLeaf(rec, el: IInterface; depth: integer);
var
  i, n: integer;
  child, linked, root: IInterface;
  rootID: cardinal;
  value, linkedFile, linkedSig, linkedID, linkedEDID, linkedName: string;
begin
  if not Assigned(el) then exit;
  if depth > 40 then exit;
  n := ElementCount(el);
  if n > 0 then begin
    for i := 0 to n - 1 do begin
      child := ElementByIndex(el, i);
      if Assigned(child) then EmitSeedLeaf(rec, child, depth + 1);
    end;
    exit;
  end;

  value := GetEditValue(el);
  if value = '' then exit;
  if Length(value) > 16384 then value := Copy(value, 1, 16384) + '...[TRUNCATED]';

  root := MasterOrSelf(rec);
  if not Assigned(root) then root := rec;
  rootID := FixedFormID(root);

  linkedFile := '';
  linkedSig := '';
  linkedID := '';
  linkedEDID := '';
  linkedName := '';
  linked := LinksTo(el);
  if Assigned(linked) then begin
    linked := EffectiveWinning(linked);
    if Assigned(linked) then begin
      linkedFile := GetFileName(GetFile(linked));
      linkedSig := Signature(linked);
      linkedID := Hex8(GetLoadOrderFormID(linked));
      linkedEDID := EditorID(linked);
      linkedName := Name(linked);
    end;
  end;

  SeedLeafOut.Add(
    Hex8(rootID) + #9 + CleanTSV(JamesSeedLabel(rootID)) + #9 +
    CleanTSV(GetFileName(GetFile(rec))) + #9 + CleanTSV(Signature(rec)) + #9 +
    Hex8(GetLoadOrderFormID(rec)) + #9 + CleanTSV(Path(el)) + #9 +
    CleanTSV(Name(el)) + #9 + CleanTSV(value) + #9 +
    CleanTSV(linkedFile) + #9 + CleanTSV(linkedSig) + #9 +
    CleanTSV(linkedID) + #9 + CleanTSV(linkedEDID) + #9 + CleanTSV(linkedName)
  );
end;

procedure ExportSeedReverseRefs(rec: IInterface);
var
  root, r: IInterface;
  rootID: cardinal;
  i, n: integer;
  fn: string;
begin
  root := MasterOrSelf(rec);
  if not Assigned(root) then root := rec;
  rootID := FixedFormID(root);
  if not IsJamesSeedFixed(rootID) then exit;

  n := ReferencedByCount(root);
  for i := 0 to n - 1 do begin
    r := ReferencedByIndex(root, i);
    if not Assigned(r) then continue;
    fn := GetFileName(GetFile(r));
    if not IsOfficialMaster(fn) then continue;
    ReverseOut.Add(
      Hex8(rootID) + #9 + CleanTSV(JamesSeedLabel(rootID)) + #9 +
      CleanTSV(GetFileName(GetFile(root))) + #9 + CleanTSV(Signature(root)) + #9 +
      CleanTSV(fn) + #9 + CleanTSV(Signature(r)) + #9 +
      Hex8(GetLoadOrderFormID(r)) + #9 + CleanTSV(EditorID(r)) + #9 +
      CleanTSV(Name(r)) + #9 + CleanTSV(FullPath(r))
    );
  end;
end;

procedure EmitCandidate(rec, el: IInterface; term, value: string);
var
  root: IInterface;
  rootID: cardinal;
begin
  root := MasterOrSelf(rec);
  if not Assigned(root) then root := rec;
  rootID := FixedFormID(root);
  if Length(value) > 4096 then value := Copy(value, 1, 4096) + '...[TRUNCATED]';
  CandidateOut.Add(
    CleanTSV(GetFileName(GetFile(rec))) + #9 + CleanTSV(Signature(rec)) + #9 +
    Hex8(GetLoadOrderFormID(rec)) + #9 + Hex8(rootID) + #9 +
    CleanTSV(EditorID(rec)) + #9 + CleanTSV(Name(rec)) + #9 +
    CleanTSV(term) + #9 + CleanTSV(Path(el)) + #9 + CleanTSV(value) + #9 +
    BoolText(IsJamesSeedFixed(rootID)) + #9 + CleanTSV(JamesSeedLabel(rootID)) + #9 +
    CleanTSV(FullPath(rec))
  );
end;

procedure ScanCandidateLeaves(rec, el: IInterface; depth: integer);
var
  i, n: integer;
  child: IInterface;
  value, term: string;
begin
  if not Assigned(el) then exit;
  if depth > 32 then exit;
  n := ElementCount(el);
  if n > 0 then begin
    for i := 0 to n - 1 do begin
      child := ElementByIndex(el, i);
      if Assigned(child) then ScanCandidateLeaves(rec, child, depth + 1);
    end;
    exit;
  end;
  value := GetEditValue(el);
  if value = '' then exit;
  term := FindStorageTerm(Name(el) + ' ' + value);
  if term <> '' then EmitCandidate(rec, el, term, value);
end;

procedure ExportPlacedRef(rec: IInterface; isVault112a: boolean);
var
  base, rootBase, rootRef: IInterface;
  baseFixed: cardinal;
  p: TwbVector;
  enableRef, refScript, baseScript, ownerRaw, term: string;
  logicalID: string;
begin
  rootRef := MasterOrSelf(rec);
  if not Assigned(rootRef) then rootRef := rec;
  logicalID := Hex8(GetLoadOrderFormID(rootRef));

  base := BaseRecord(rec);
  if not Assigned(base) then exit;
  rootBase := MasterOrSelf(base);
  if not Assigned(rootBase) then rootBase := base;
  baseFixed := FixedFormID(rootBase);

  p := GetPosition(rec);
  enableRef := FirstNonEmpty(
    SafePathValue(rec, 'XESP - Enable Parent\Reference'),
    SafePathValue(rec, 'Enable Parent\Reference'),
    SafePathValue(rec, 'XESP\Reference')
  );
  refScript := FirstNonEmpty(SafePathValue(rec, 'SCRI - Script'), SafePathValue(rec, 'Script'), '');
  baseScript := FirstNonEmpty(SafePathValue(rootBase, 'SCRI - Script'), SafePathValue(rootBase, 'Script'), '');
  ownerRaw := FirstNonEmpty(SafePathValue(rec, 'XOWN - Owner'), SafePathValue(rec, 'Ownership\Owner'), SafePathValue(rec, 'Ownership'));
  term := FindStorageTerm(EditorID(rec) + ' ' + Name(rec) + ' ' + EditorID(rootBase) + ' ' + Name(rootBase));

  if IsJamesSeedFixed(baseFixed) or (FixedFormID(rootRef) = $0006023C) then begin
    PlacedSeedOut.Add(
      logicalID + #9 + CleanTSV(GetFileName(GetFile(rec))) + #9 +
      Hex8(baseFixed) + #9 + CleanTSV(JamesSeedLabel(baseFixed)) + #9 +
      CleanTSV(EditorID(rootBase)) + #9 + CleanTSV(Name(rootBase)) + #9 +
      CleanTSV(CanonicalLocationKey(rec)) + #9 + CleanTSV(CanonicalCellEditorID(rec)) + #9 +
      FloatInvariant(p.x) + #9 + FloatInvariant(p.y) + #9 + FloatInvariant(p.z) + #9 +
      BoolText(GetIsInitiallyDisabled(rec)) + #9 + CleanTSV(enableRef) + #9 +
      CleanTSV(ownerRaw) + #9 + CleanTSV(refScript) + #9 + CleanTSV(baseScript) + #9 +
      CleanTSV(FullPath(rec))
    );
  end;

  if isVault112a then begin
    Vault112RefOut.Add(
      logicalID + #9 + CleanTSV(GetFileName(GetFile(rec))) + #9 +
      CleanTSV(Signature(rootBase)) + #9 + Hex8(baseFixed) + #9 +
      CleanTSV(EditorID(rootBase)) + #9 + CleanTSV(Name(rootBase)) + #9 +
      FloatInvariant(p.x) + #9 + FloatInvariant(p.y) + #9 + FloatInvariant(p.z) + #9 +
      BoolText(GetIsInitiallyDisabled(rec)) + #9 + CleanTSV(enableRef) + #9 +
      CleanTSV(ownerRaw) + #9 + CleanTSV(refScript) + #9 + CleanTSV(baseScript) + #9 +
      CleanTSV(term) + #9 + CleanTSV(FullPath(rec))
    );
  end;
end;

function Initialize: integer;
var
  i: integer;
  f: IInterface;
  fn: string;
begin
  Result := 0;
  Blocked := false;
  DuplicateLogicalCount := 0;

  SeedLeafOut := TStringList.Create;
  ReverseOut := TStringList.Create;
  PlacedSeedOut := TStringList.Create;
  Vault112RefOut := TStringList.Create;
  CandidateOut := TStringList.Create;
  LoadedOfficial := TStringList.Create;
  UnexpectedPlugins := TStringList.Create;
  SeenLogical := TStringList.Create;
  SeenCandidateRecords := TStringList.Create;
  StorageTerms := TStringList.Create;

  LoadedOfficial.Sorted := true;
  LoadedOfficial.Duplicates := dupIgnore;
  UnexpectedPlugins.Sorted := true;
  UnexpectedPlugins.Duplicates := dupIgnore;
  SeenLogical.Sorted := true;
  SeenLogical.Duplicates := dupIgnore;
  SeenCandidateRecords.Sorted := true;
  SeenCandidateRecords.Duplicates := dupIgnore;
  StorageTerms.Sorted := true;
  StorageTerms.Duplicates := dupIgnore;
  AddStorageTerms;

  if CompareText(wbAppName, 'FO3') <> 0 then begin
    AddMessage('JANUS James storage v1.7 BLOCKED: xEdit is not running in FO3 mode.');
    Blocked := true;
  end;

  for i := 0 to FileCount - 1 do begin
    f := FileByIndex(i);
    if not Assigned(f) then continue;
    fn := GetFileName(f);
    if IsOfficialMaster(fn) then LoadedOfficial.Add(fn)
    else if IsPluginFilename(fn) then UnexpectedPlugins.Add(fn);
  end;
  if LoadedOfficial.Count <> 6 then begin
    AddMessage('JANUS James storage v1.7 BLOCKED: expected six official masters, found ' + IntToStr(LoadedOfficial.Count) + '.');
    Blocked := true;
  end;
  if UnexpectedPlugins.Count > 0 then begin
    AddMessage('JANUS James storage v1.7 BLOCKED: non-official plugins loaded.');
    Blocked := true;
  end;

  SeedLeafOut.Add('seed_fixed_formid' + #9 + 'seed_label' + #9 + 'record_file' + #9 + 'record_signature' + #9 + 'record_formid' + #9 + 'element_path' + #9 + 'element_name' + #9 + 'element_value' + #9 + 'linked_file' + #9 + 'linked_signature' + #9 + 'linked_formid' + #9 + 'linked_editorid' + #9 + 'linked_name');
  ReverseOut.Add('seed_fixed_formid' + #9 + 'seed_label' + #9 + 'seed_file' + #9 + 'seed_signature' + #9 + 'referencing_file' + #9 + 'referencing_signature' + #9 + 'referencing_formid' + #9 + 'referencing_editorid' + #9 + 'referencing_name' + #9 + 'referencing_full_path');
  PlacedSeedOut.Add('logical_ref_formid' + #9 + 'winning_file' + #9 + 'base_fixed_formid' + #9 + 'base_seed_label' + #9 + 'base_editorid' + #9 + 'base_name' + #9 + 'location_key' + #9 + 'cell_editorid' + #9 + 'position_x' + #9 + 'position_y' + #9 + 'position_z' + #9 + 'initially_disabled' + #9 + 'enable_parent_raw' + #9 + 'owner_raw' + #9 + 'ref_script_raw' + #9 + 'base_script_raw' + #9 + 'full_path');
  Vault112RefOut.Add('logical_ref_formid' + #9 + 'winning_file' + #9 + 'base_signature' + #9 + 'base_fixed_formid' + #9 + 'base_editorid' + #9 + 'base_name' + #9 + 'position_x' + #9 + 'position_y' + #9 + 'position_z' + #9 + 'initially_disabled' + #9 + 'enable_parent_raw' + #9 + 'owner_raw' + #9 + 'ref_script_raw' + #9 + 'base_script_raw' + #9 + 'storage_identity_term' + #9 + 'full_path');
  CandidateOut.Add('record_file' + #9 + 'record_signature' + #9 + 'record_formid' + #9 + 'root_fixed_formid' + #9 + 'record_editorid' + #9 + 'record_name' + #9 + 'matched_term' + #9 + 'element_path' + #9 + 'element_value' + #9 + 'is_seed_record' + #9 + 'seed_label' + #9 + 'record_full_path');

  AddMessage('JANUS James session storage-association exporter v1.7 initialized.');
end;

function Process(e: IInterface): integer;
var
  win, root: IInterface;
  rootID: cardinal;
  logicalID, identityTerm: string;
  isVault112a: boolean;
begin
  Result := 0;
  if Blocked then exit;
  if ElementType(e) <> etMainRecord then exit;
  if not IsOfficialMaster(GetFileName(GetFile(e))) then exit;

  win := EffectiveWinning(e);
  if not Assigned(win) then exit;
  if not IsSameRecord(e, win) then exit;

  root := MasterOrSelf(win);
  if not Assigned(root) then root := win;
  rootID := FixedFormID(root);
  logicalID := CleanTSV(GetFileName(GetFile(root))) + '|' + Hex8(GetLoadOrderFormID(root));
  if SeenLogical.IndexOf(logicalID) >= 0 then begin
    DuplicateLogicalCount := DuplicateLogicalCount + 1;
    exit;
  end;
  SeenLogical.Add(logicalID);

  if IsJamesSeedFixed(rootID) then begin
    EmitSeedLeaf(win, win, 0);
    ExportSeedReverseRefs(win);
  end;

  if Signature(win) = 'REFR' then begin
    isVault112a := CompareText(CanonicalCellEditorID(win), 'Vault112a') = 0;
    ExportPlacedRef(win, isVault112a);
  end;

  identityTerm := FindStorageTerm(EditorID(win) + ' ' + Name(win));
  if identityTerm <> '' then
    EmitCandidate(win, win, identityTerm, EditorID(win) + ' | ' + Name(win));
  ScanCandidateLeaves(win, win, 0);
end;

function Finalize: integer;
var
  seedFn, reverseFn, placedFn, vaultFn, candidateFn: string;
begin
  Result := 0;
  if Blocked then begin
    AddMessage('JANUS James storage v1.7 export NOT WRITTEN: admission prerequisites failed.');
  end else if DuplicateLogicalCount <> 0 then begin
    AddMessage('JANUS James storage v1.7 export NOT WRITTEN: duplicate logical records = ' + IntToStr(DuplicateLogicalCount));
  end else begin
    seedFn := ScriptsPath + 'JANUS-James-Session-Seed-Leaves-v1.7.tsv';
    reverseFn := ScriptsPath + 'JANUS-James-Session-Seed-Reverse-Refs-v1.7.tsv';
    placedFn := ScriptsPath + 'JANUS-James-Placed-Seed-Refs-v1.7.tsv';
    vaultFn := ScriptsPath + 'JANUS-Vault112a-REFR-Inventory-v1.7.tsv';
    candidateFn := ScriptsPath + 'JANUS-James-Storage-Candidates-v1.7.tsv';
    SeedLeafOut.SaveToFile(seedFn);
    ReverseOut.SaveToFile(reverseFn);
    PlacedSeedOut.SaveToFile(placedFn);
    Vault112RefOut.SaveToFile(vaultFn);
    CandidateOut.SaveToFile(candidateFn);
    AddMessage('Seed leaves: ' + IntToStr(SeedLeafOut.Count - 1));
    AddMessage('Seed reverse refs: ' + IntToStr(ReverseOut.Count - 1));
    AddMessage('Placed seed refs: ' + IntToStr(PlacedSeedOut.Count - 1));
    AddMessage('Vault112a REFR rows: ' + IntToStr(Vault112RefOut.Count - 1));
    AddMessage('Storage candidate hits: ' + IntToStr(CandidateOut.Count - 1));
  end;

  SeedLeafOut.Free;
  ReverseOut.Free;
  PlacedSeedOut.Free;
  Vault112RefOut.Free;
  CandidateOut.Free;
  LoadedOfficial.Free;
  UnexpectedPlugins.Free;
  SeenLogical.Free;
  SeenCandidateRecords.Free;
  StorageTerms.Free;
end;

end.
