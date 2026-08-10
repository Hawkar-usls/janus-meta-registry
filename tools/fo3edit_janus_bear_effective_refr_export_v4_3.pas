unit fo3edit_janus_bear_effective_refr_export_v4_3;

{
  JANUS Bear v4.3 — read-only effective REFR inventory exporter.

  Intended load set:
    Fallout3.esm
    Anchorage.esm
    ThePitt.esm
    BrokenSteel.esm
    PointLookout.esm
    Zeta.esm

  Semantics:
    * every logical REFR is emitted at most once;
    * unoverridden master records are emitted;
    * when a REFR has overrides, only the winning override is emitted;
    * a winning deleted REFR suppresses the logical reference and is counted,
      not resurrected from an older version;
    * location_key is canonicalized to the master-or-self CELL/WRLD identity,
      so CELL overrides do not split one logical location into multiple keys;
    * no record is modified.

  Output:
    Edit Scripts\JANUS-Bear-Effective-REFR-v4.3.tsv
}

var
  OutList: TStringList;
  SeenLogical: TStringList;
  LoadedOfficial: TStringList;
  UnexpectedPlugins: TStringList;
  WinningFileRows: TStringList;
  DuplicateLogicalCount: integer;
  DeletedWinningSuppressed: integer;
  Blocked: boolean;

function CleanTSV(s: string): string;
begin
  s := StringReplace(s, #9, ' ', [rfReplaceAll]);
  s := StringReplace(s, #13, ' ', [rfReplaceAll]);
  s := StringReplace(s, #10, ' ', [rfReplaceAll]);
  Result := s;
end;

function BoolText(b: boolean): string;
begin
  if b then Result := 'true' else Result := 'false';
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

function TargetKind(id: cardinal): string;
begin
  Result := 'OTHER';
  if id = $0001F21F then Result := 'TEDDY'
  else if id = $0001EDEA then Result := 'SKELETON_CLOTHES'
  else if id = $0001EDE3 then Result := 'SKELETON_RAGS'
  else if id = $0002EC65 then Result := 'SKELETON_MALE'
  else if id = $0003DD2D then Result := 'SKELETON_FEMALE'
  else if id = $0003407A then Result := 'GNOME_GENERIC'
  else if id = $0005B634 then Result := 'GNOME_INTACT'
  else if id = $0005B635 then Result := 'GNOME_DAMAGED';
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
        Result :=
          sig + '|' +
          CleanTSV(GetFileName(GetFile(rootLoc))) + '|' +
          Hex8(GetLoadOrderFormID(rootLoc));
        exit;
      end;
    end;
    c := GetContainer(c);
  end;
end;

function CanonicalLocationEditorID(e: IInterface): string;
var
  c: IInterface;
  sig: string;
begin
  Result := '';
  c := GetContainer(e);
  while Assigned(c) do begin
    if ElementType(c) = etMainRecord then begin
      sig := Signature(c);
      if (sig = 'CELL') or (sig = 'WRLD') then begin
        Result := CleanTSV(EditorID(c));
        exit;
      end;
    end;
    c := GetContainer(c);
  end;
end;

procedure IncNamedCounter(list: TStringList; key: string);
var
  i, n: integer;
begin
  i := list.IndexOfName(key);
  if i < 0 then
    list.Values[key] := '1'
  else begin
    n := StrToIntDef(list.ValueFromIndex[i], 0);
    list.Values[key] := IntToStr(n + 1);
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
  DeletedWinningSuppressed := 0;

  OutList := TStringList.Create;
  SeenLogical := TStringList.Create;
  LoadedOfficial := TStringList.Create;
  UnexpectedPlugins := TStringList.Create;
  WinningFileRows := TStringList.Create;

  SeenLogical.Sorted := true;
  SeenLogical.Duplicates := dupIgnore;
  LoadedOfficial.Sorted := true;
  LoadedOfficial.Duplicates := dupIgnore;
  UnexpectedPlugins.Sorted := true;
  UnexpectedPlugins.Duplicates := dupIgnore;

  if CompareText(wbAppName, 'FO3') <> 0 then begin
    AddMessage('JANUS v4.3 BLOCKED: xEdit is not running in FO3 mode.');
    Blocked := true;
  end;

  for i := 0 to FileCount - 1 do begin
    f := FileByIndex(i);
    if not Assigned(f) then continue;
    fn := GetFileName(f);
    if IsOfficialMaster(fn) then
      LoadedOfficial.Add(fn)
    else if IsPluginFilename(fn) then
      UnexpectedPlugins.Add(fn);
  end;

  if LoadedOfficial.Count <> 6 then begin
    AddMessage('JANUS v4.3 BLOCKED: expected six official masters, found ' + IntToStr(LoadedOfficial.Count) + '.');
    Blocked := true;
  end;

  if UnexpectedPlugins.Count > 0 then begin
    AddMessage('JANUS v4.3 BLOCKED: non-official .esm/.esp files are loaded.');
    for i := 0 to UnexpectedPlugins.Count - 1 do
      AddMessage('  unexpected plugin: ' + UnexpectedPlugins[i]);
    Blocked := true;
  end;

  OutList.Add(
    'record_file' + #9 +
    'record_signature' + #9 +
    'record_formid' + #9 +
    'record_editorid' + #9 +
    'target_kind' + #9 +
    'base_file' + #9 +
    'base_signature' + #9 +
    'base_formid' + #9 +
    'base_editorid' + #9 +
    'base_name' + #9 +
    'location_key' + #9 +
    'initially_disabled' + #9 +
    'deleted' + #9 +
    'persistent' + #9 +
    'position_x' + #9 +
    'position_y' + #9 +
    'position_z' + #9 +
    'full_path' + #9 +
    'logical_ref_formid' + #9 +
    'origin_record_file' + #9 +
    'winning_record_file' + #9 +
    'override_count' + #9 +
    'location_editorid'
  );

  AddMessage('JANUS Bear v4.3 effective REFR exporter initialized.');
  AddMessage('Loaded official masters: ' + IntToStr(LoadedOfficial.Count));
end;

function Process(e: IInterface): integer;
var
  recFile, originFile, baseFile, kind, logicalID: string;
  base, rootBase, rootRef: IInterface;
  baseFixed: cardinal;
  p: TwbVector;
  ovCount: integer;
begin
  Result := 0;
  if Blocked then exit;
  if ElementType(e) <> etMainRecord then exit;
  if Signature(e) <> 'REFR' then exit;

  recFile := GetFileName(GetFile(e));
  if not IsOfficialMaster(recFile) then exit;

  rootRef := MasterOrSelf(e);
  if not Assigned(rootRef) then rootRef := e;
  originFile := GetFileName(GetFile(rootRef));
  if not IsOfficialMaster(originFile) then exit;

  ovCount := OverrideCount(rootRef);

  if IsMaster(e) then begin
    if ovCount > 0 then exit;
  end else begin
    if not IsWinningOverride(e) then exit;
  end;

  logicalID := Hex8(GetLoadOrderFormID(rootRef));
  if SeenLogical.IndexOf(logicalID) >= 0 then begin
    DuplicateLogicalCount := DuplicateLogicalCount + 1;
    exit;
  end;
  SeenLogical.Add(logicalID);

  if GetIsDeleted(e) then begin
    DeletedWinningSuppressed := DeletedWinningSuppressed + 1;
    exit;
  end;

  base := BaseRecord(e);
  if not Assigned(base) then exit;
  rootBase := MasterOrSelf(base);
  if not Assigned(rootBase) then rootBase := base;

  baseFile := GetFileName(GetFile(rootBase));
  baseFixed := FixedFormID(rootBase);
  kind := TargetKind(baseFixed);
  p := GetPosition(e);

  IncNamedCounter(WinningFileRows, recFile);

  OutList.Add(
    CleanTSV(recFile) + #9 +
    'REFR' + #9 +
    Hex8(GetLoadOrderFormID(e)) + #9 +
    CleanTSV(EditorID(e)) + #9 +
    kind + #9 +
    CleanTSV(baseFile) + #9 +
    CleanTSV(Signature(rootBase)) + #9 +
    Hex8(baseFixed) + #9 +
    CleanTSV(EditorID(rootBase)) + #9 +
    '' + #9 +
    CleanTSV(CanonicalLocationKey(e)) + #9 +
    BoolText(GetIsInitiallyDisabled(e)) + #9 +
    'false' + #9 +
    BoolText(GetIsPersistent(e)) + #9 +
    FloatInvariant(p.x) + #9 +
    FloatInvariant(p.y) + #9 +
    FloatInvariant(p.z) + #9 +
    CleanTSV(FullPath(e)) + #9 +
    logicalID + #9 +
    CleanTSV(originFile) + #9 +
    CleanTSV(recFile) + #9 +
    IntToStr(ovCount) + #9 +
    CanonicalLocationEditorID(e)
  );
end;

function Finalize: integer;
var
  fn: string;
  i: integer;
begin
  Result := 0;

  if Blocked then begin
    AddMessage('JANUS Bear v4.3 export NOT WRITTEN because admission prerequisites failed.');
  end else if DuplicateLogicalCount <> 0 then begin
    AddMessage('JANUS Bear v4.3 export NOT WRITTEN: duplicate logical REFR identities detected: ' + IntToStr(DuplicateLogicalCount));
  end else begin
    fn := ScriptsPath + 'JANUS-Bear-Effective-REFR-v4.3.tsv';
    OutList.SaveToFile(fn);
    AddMessage('JANUS Bear v4.3 effective REFR inventory written: ' + fn);
    AddMessage('Effective rows excluding header: ' + IntToStr(OutList.Count - 1));
    AddMessage('Winning deleted logical refs suppressed: ' + IntToStr(DeletedWinningSuppressed));
    AddMessage('Duplicate logical refs: ' + IntToStr(DuplicateLogicalCount));
    for i := 0 to WinningFileRows.Count - 1 do
      AddMessage('Winning rows ' + WinningFileRows.Names[i] + ': ' + WinningFileRows.ValueFromIndex[i]);
  end;

  OutList.Free;
  SeenLogical.Free;
  LoadedOfficial.Free;
  UnexpectedPlugins.Free;
  WinningFileRows.Free;
end;

end.
