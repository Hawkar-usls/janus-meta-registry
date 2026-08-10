unit fo3edit_vault112_blind_spatial_neighborhood_export_v2_1;

{
  JANUS / Fallout 3
  Vault 112 blind spatial-neighborhood exporter v2.1

  Read-only. Load exactly the six official Fallout 3 masters.

  Purpose:
    Export EVERY winning placed REFR in CELL Vault112a without name/type
    preclassification. This closes the v2.0 blind spot where an unnamed
    ACTI/STAT/MSTT or other generic prop could be skipped before spatial
    analysis.

  Output:
    JANUS-Vault112a-All-Refs-v2.1.tsv

  Hard boundary:
    Exporting proximity does not establish functional wiring, persistence,
    memory ownership, or carrier association.
}

var
  AllRefsOut: TStringList;
  LoadedOfficial: TStringList;
  UnexpectedPlugins: TStringList;
  SeenLogical: TStringList;
  Blocked: boolean;
  DuplicateLogicalCount: integer;

function CleanTSV(s: string): string;
begin
  s := StringReplace(s, #9, ' ', [rfReplaceAll]);
  s := StringReplace(s, #13, ' ', [rfReplaceAll]);
  s := StringReplace(s, #10, ' ', [rfReplaceAll]);
  Result := s;
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

function CanonicalCellEditorID(e: IInterface): string;
var
  c, rootCell: IInterface;
begin
  Result := '';
  c := GetContainer(e);
  while Assigned(c) do begin
    if (ElementType(c) = etMainRecord) and (Signature(c) = 'CELL') then begin
      rootCell := MasterOrSelf(c);
      if not Assigned(rootCell) then rootCell := c;
      Result := EditorID(rootCell);
      exit;
    end;
    c := GetContainer(c);
  end;
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

procedure ExportAllRef(rec: IInterface);
var
  base, rootBase, rootRef: IInterface;
  p: TwbVector;
  baseSig, baseForm, baseEDID, baseName, baseModel: string;
  enableRaw, ownerRaw, refScriptRaw, baseScriptRaw: string;
begin
  rootRef := MasterOrSelf(rec);
  if not Assigned(rootRef) then rootRef := rec;

  base := BaseRecord(rec);
  rootBase := nil;
  baseSig := '';
  baseForm := '';
  baseEDID := '';
  baseName := '';
  baseModel := '';
  baseScriptRaw := '';

  if Assigned(base) then begin
    rootBase := MasterOrSelf(base);
    if not Assigned(rootBase) then rootBase := base;
    baseSig := Signature(rootBase);
    baseForm := Hex8(FixedFormID(rootBase));
    baseEDID := EditorID(rootBase);
    baseName := Name(rootBase);
    baseModel := FirstNonEmpty(
      SafePathValue(rootBase, 'Model\MODL - Model Filename'),
      SafePathValue(rootBase, 'MODL - Model Filename'),
      SafePathValue(rootBase, 'Model\MODL')
    );
    baseScriptRaw := FirstNonEmpty(
      SafePathValue(rootBase, 'SCRI - Script'),
      SafePathValue(rootBase, 'Script'),
      ''
    );
  end;

  p := GetPosition(rec);
  enableRaw := FirstNonEmpty(
    SafePathValue(rec, 'XESP - Enable Parent\Reference'),
    SafePathValue(rec, 'Enable Parent\Reference'),
    SafePathValue(rec, 'XESP\Reference')
  );
  ownerRaw := FirstNonEmpty(
    SafePathValue(rec, 'XOWN - Owner'),
    SafePathValue(rec, 'Ownership\Owner'),
    SafePathValue(rec, 'Ownership')
  );
  refScriptRaw := FirstNonEmpty(
    SafePathValue(rec, 'SCRI - Script'),
    SafePathValue(rec, 'Script'),
    ''
  );

  AllRefsOut.Add(
    Hex8(GetLoadOrderFormID(rootRef)) + #9 +
    CleanTSV(GetFileName(GetFile(rec))) + #9 +
    CleanTSV(baseSig) + #9 +
    CleanTSV(baseForm) + #9 +
    CleanTSV(baseEDID) + #9 +
    CleanTSV(baseName) + #9 +
    CleanTSV(EditorID(rec)) + #9 +
    CleanTSV(Name(rec)) + #9 +
    FloatInvariant(p.x) + #9 +
    FloatInvariant(p.y) + #9 +
    FloatInvariant(p.z) + #9 +
    BoolText(GetIsInitiallyDisabled(rec)) + #9 +
    CleanTSV(enableRaw) + #9 +
    CleanTSV(ownerRaw) + #9 +
    CleanTSV(refScriptRaw) + #9 +
    CleanTSV(baseScriptRaw) + #9 +
    CleanTSV(baseModel) + #9 +
    CleanTSV(FullPath(rec))
  );
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

  AllRefsOut := TStringList.Create;
  LoadedOfficial := TStringList.Create;
  UnexpectedPlugins := TStringList.Create;
  SeenLogical := TStringList.Create;

  LoadedOfficial.Sorted := true;
  LoadedOfficial.Duplicates := dupIgnore;
  UnexpectedPlugins.Sorted := true;
  UnexpectedPlugins.Duplicates := dupIgnore;
  SeenLogical.Sorted := true;
  SeenLogical.Duplicates := dupIgnore;

  if CompareText(wbAppName, 'FO3') <> 0 then begin
    AddMessage('JANUS Vault112 blind-neighborhood v2.1 BLOCKED: xEdit is not running in FO3 mode.');
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
    AddMessage('JANUS Vault112 blind-neighborhood v2.1 BLOCKED: expected six official masters, found ' + IntToStr(LoadedOfficial.Count) + '.');
    Blocked := true;
  end;
  if UnexpectedPlugins.Count > 0 then begin
    AddMessage('JANUS Vault112 blind-neighborhood v2.1 BLOCKED: non-official plugins loaded.');
    Blocked := true;
  end;

  AllRefsOut.Add(
    'logical_ref_formid' + #9 +
    'winning_file' + #9 +
    'base_signature' + #9 +
    'base_fixed_formid' + #9 +
    'base_editorid' + #9 +
    'base_name' + #9 +
    'ref_editorid' + #9 +
    'ref_name' + #9 +
    'position_x' + #9 +
    'position_y' + #9 +
    'position_z' + #9 +
    'initially_disabled' + #9 +
    'enable_parent_raw' + #9 +
    'owner_raw' + #9 +
    'ref_script_raw' + #9 +
    'base_script_raw' + #9 +
    'base_model_raw' + #9 +
    'full_path'
  );

  AddMessage('JANUS Vault112 blind spatial-neighborhood exporter v2.1 initialized.');
end;

function Process(e: IInterface): integer;
var
  win, root: IInterface;
  logicalKey: string;
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
  logicalKey := GetFileName(GetFile(root)) + '|' + Hex8(GetLoadOrderFormID(root));

  if SeenLogical.IndexOf(logicalKey) >= 0 then begin
    DuplicateLogicalCount := DuplicateLogicalCount + 1;
    exit;
  end;
  SeenLogical.Add(logicalKey);

  if (Signature(win) = 'REFR') and
     (CompareText(CanonicalCellEditorID(win), 'Vault112a') = 0) then
    ExportAllRef(win);
end;

function Finalize: integer;
var
  outFn: string;
begin
  Result := 0;

  if Blocked then begin
    AddMessage('JANUS Vault112 blind-neighborhood v2.1 export NOT WRITTEN: prerequisites failed.');
  end else if DuplicateLogicalCount <> 0 then begin
    AddMessage('JANUS Vault112 blind-neighborhood v2.1 export NOT WRITTEN: duplicate logical records = ' + IntToStr(DuplicateLogicalCount));
  end else begin
    outFn := ScriptsPath + 'JANUS-Vault112a-All-Refs-v2.1.tsv';
    AllRefsOut.SaveToFile(outFn);
    AddMessage('Vault112a all-REFR rows: ' + IntToStr(AllRefsOut.Count - 1));
  end;

  AllRefsOut.Free;
  LoadedOfficial.Free;
  UnexpectedPlugins.Free;
  SeenLogical.Free;
end;

end.
