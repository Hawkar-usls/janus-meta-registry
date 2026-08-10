unit fo3edit_janus_bear_scene_lifecycle_export_v4_7;

{
  JANUS Bear v4.7 — read-only teddy/gnome REFR lifecycle + reverse-reference exporter.

  Load exactly:
    Fallout3.esm
    Anchorage.esm
    ThePitt.esm
    BrokenSteel.esm
    PointLookout.esm
    Zeta.esm

  Apply to loaded files/groups. The script emits effective winning logical REFRs
  for the teddy and three Fallout 3 garden-gnome base records only.

  Outputs:
    Edit Scripts\JANUS-Bear-Scene-Lifecycle-v4.7.tsv
    Edit Scripts\JANUS-Bear-Scene-Reverse-Refs-v4.7.tsv

  It never modifies a game record.
}

var
  LifecycleOut: TStringList;
  ReverseOut: TStringList;
  SeenLogical: TStringList;
  LoadedOfficial: TStringList;
  UnexpectedPlugins: TStringList;
  Blocked: boolean;
  DuplicateLogicalCount: integer;

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
  Result := '';
  if id = $0001F21F then Result := 'TEDDY'
  else if id = $0003407A then Result := 'GNOME_GENERIC'
  else if id = $0005B634 then Result := 'GNOME_INTACT'
  else if id = $0005B635 then Result := 'GNOME_DAMAGED';
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

function FirstNonEmpty(a, b, c: string): string;
begin
  Result := a;
  if Result = '' then Result := b;
  if Result = '' then Result := c;
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

function CanonicalLocationEditorID(e: IInterface): string;
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
        Result := CleanTSV(EditorID(rootLoc));
        exit;
      end;
    end;
    c := GetContainer(c);
  end;
end;

procedure ExportReverseRefs(target: IInterface; logicalID, kind: string);
var
  rootTarget, r: IInterface;
  i, n: integer;
  fn: string;
begin
  rootTarget := MasterOrSelf(target);
  if not Assigned(rootTarget) then rootTarget := target;
  n := ReferencedByCount(rootTarget);
  for i := 0 to n - 1 do begin
    r := ReferencedByIndex(rootTarget, i);
    if not Assigned(r) then continue;
    fn := GetFileName(GetFile(r));
    if not IsOfficialMaster(fn) then continue;
    ReverseOut.Add(
      logicalID + #9 +
      kind + #9 +
      CleanTSV(fn) + #9 +
      CleanTSV(Signature(r)) + #9 +
      Hex8(GetLoadOrderFormID(r)) + #9 +
      CleanTSV(EditorID(r)) + #9 +
      CleanTSV(Name(r)) + #9 +
      CleanTSV(FullPath(r))
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

  LifecycleOut := TStringList.Create;
  ReverseOut := TStringList.Create;
  SeenLogical := TStringList.Create;
  LoadedOfficial := TStringList.Create;
  UnexpectedPlugins := TStringList.Create;

  SeenLogical.Sorted := true;
  SeenLogical.Duplicates := dupIgnore;
  LoadedOfficial.Sorted := true;
  LoadedOfficial.Duplicates := dupIgnore;
  UnexpectedPlugins.Sorted := true;
  UnexpectedPlugins.Duplicates := dupIgnore;

  if CompareText(wbAppName, 'FO3') <> 0 then begin
    AddMessage('JANUS Bear v4.7 BLOCKED: xEdit is not running in FO3 mode.');
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
    AddMessage('JANUS Bear v4.7 BLOCKED: expected six official masters, found ' + IntToStr(LoadedOfficial.Count) + '.');
    Blocked := true;
  end;
  if UnexpectedPlugins.Count > 0 then begin
    AddMessage('JANUS Bear v4.7 BLOCKED: non-official plugin files are loaded.');
    Blocked := true;
  end;

  LifecycleOut.Add(
    'logical_ref_formid' + #9 +
    'target_kind' + #9 +
    'origin_record_file' + #9 +
    'winning_record_file' + #9 +
    'winning_record_formid' + #9 +
    'base_file' + #9 +
    'base_formid' + #9 +
    'base_editorid' + #9 +
    'location_key' + #9 +
    'location_editorid' + #9 +
    'position_x' + #9 +
    'position_y' + #9 +
    'position_z' + #9 +
    'initially_disabled' + #9 +
    'persistent' + #9 +
    'override_count' + #9 +
    'enable_parent_reference_raw' + #9 +
    'enable_parent_flags_raw' + #9 +
    'owner_raw' + #9 +
    'ref_script_raw' + #9 +
    'base_script_raw' + #9 +
    'direct_reverse_reference_count' + #9 +
    'full_path'
  );

  ReverseOut.Add(
    'target_logical_ref_formid' + #9 +
    'target_kind' + #9 +
    'referencing_file' + #9 +
    'referencing_signature' + #9 +
    'referencing_formid' + #9 +
    'referencing_editorid' + #9 +
    'referencing_name' + #9 +
    'referencing_full_path'
  );

  AddMessage('JANUS Bear v4.7 lifecycle exporter initialized.');
end;

function Process(e: IInterface): integer;
var
  recFile, originFile, kind, logicalID: string;
  base, rootBase, rootRef: IInterface;
  baseFixed: cardinal;
  p: TwbVector;
  ovCount, reverseCount: integer;
  enableRef, enableFlags, ownerValue, refScript, baseScript: string;
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

  if GetIsDeleted(e) then exit;

  base := BaseRecord(e);
  if not Assigned(base) then exit;
  rootBase := MasterOrSelf(base);
  if not Assigned(rootBase) then rootBase := base;
  baseFixed := FixedFormID(rootBase);
  kind := TargetKind(baseFixed);
  if kind = '' then exit;

  logicalID := Hex8(GetLoadOrderFormID(rootRef));
  if SeenLogical.IndexOf(logicalID) >= 0 then begin
    DuplicateLogicalCount := DuplicateLogicalCount + 1;
    exit;
  end;
  SeenLogical.Add(logicalID);

  p := GetPosition(e);

  enableRef := FirstNonEmpty(
    SafePathValue(e, 'XESP - Enable Parent\Reference'),
    SafePathValue(e, 'Enable Parent\Reference'),
    SafePathValue(e, 'XESP\Reference')
  );
  enableFlags := FirstNonEmpty(
    SafePathValue(e, 'XESP - Enable Parent\Flags'),
    SafePathValue(e, 'Enable Parent\Flags'),
    SafePathValue(e, 'XESP\Flags')
  );
  ownerValue := FirstNonEmpty(
    SafePathValue(e, 'XOWN - Owner'),
    SafePathValue(e, 'Ownership\Owner'),
    SafePathValue(e, 'Ownership')
  );
  refScript := FirstNonEmpty(
    SafePathValue(e, 'SCRI - Script'),
    SafePathValue(e, 'Script'),
    ''
  );
  baseScript := FirstNonEmpty(
    SafePathValue(rootBase, 'SCRI - Script'),
    SafePathValue(rootBase, 'Script'),
    ''
  );

  reverseCount := ReferencedByCount(rootRef);

  LifecycleOut.Add(
    logicalID + #9 +
    kind + #9 +
    CleanTSV(originFile) + #9 +
    CleanTSV(recFile) + #9 +
    Hex8(GetLoadOrderFormID(e)) + #9 +
    CleanTSV(GetFileName(GetFile(rootBase))) + #9 +
    Hex8(baseFixed) + #9 +
    CleanTSV(EditorID(rootBase)) + #9 +
    CleanTSV(CanonicalLocationKey(e)) + #9 +
    CleanTSV(CanonicalLocationEditorID(e)) + #9 +
    FloatInvariant(p.x) + #9 +
    FloatInvariant(p.y) + #9 +
    FloatInvariant(p.z) + #9 +
    BoolText(GetIsInitiallyDisabled(e)) + #9 +
    BoolText(GetIsPersistent(e)) + #9 +
    IntToStr(ovCount) + #9 +
    CleanTSV(enableRef) + #9 +
    CleanTSV(enableFlags) + #9 +
    CleanTSV(ownerValue) + #9 +
    CleanTSV(refScript) + #9 +
    CleanTSV(baseScript) + #9 +
    IntToStr(reverseCount) + #9 +
    CleanTSV(FullPath(e))
  );

  ExportReverseRefs(e, logicalID, kind);
end;

function Finalize: integer;
var
  lifecycleFn, reverseFn: string;
begin
  Result := 0;
  if Blocked then begin
    AddMessage('JANUS Bear v4.7 export NOT WRITTEN: admission prerequisites failed.');
  end else if DuplicateLogicalCount <> 0 then begin
    AddMessage('JANUS Bear v4.7 export NOT WRITTEN: duplicate logical target REFRs = ' + IntToStr(DuplicateLogicalCount));
  end else begin
    lifecycleFn := ScriptsPath + 'JANUS-Bear-Scene-Lifecycle-v4.7.tsv';
    reverseFn := ScriptsPath + 'JANUS-Bear-Scene-Reverse-Refs-v4.7.tsv';
    LifecycleOut.SaveToFile(lifecycleFn);
    ReverseOut.SaveToFile(reverseFn);
    AddMessage('JANUS Bear v4.7 lifecycle rows: ' + IntToStr(LifecycleOut.Count - 1));
    AddMessage('JANUS Bear v4.7 reverse-reference edges: ' + IntToStr(ReverseOut.Count - 1));
    AddMessage('Lifecycle TSV: ' + lifecycleFn);
    AddMessage('Reverse-ref TSV: ' + reverseFn);
  end;

  LifecycleOut.Free;
  ReverseOut.Free;
  SeenLogical.Free;
  LoadedOfficial.Free;
  UnexpectedPlugins.Free;
end;

end.
