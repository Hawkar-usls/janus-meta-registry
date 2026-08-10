unit JANUS_Teddy_Context_Inventory_Export;

{
  Read-only reference inventory exporter for Fallout 3 Janus Bear spatial analysis.

  Load/select official Fallout 3 masters:
    Fallout3.esm, Anchorage.esm, ThePitt.esm, BrokenSteel.esm,
    PointLookout.esm, Zeta.esm

  Output:
    Edit Scripts\JANUS-Teddy-Context-Inventory.tsv

  The script exports every placed REFR physically contained by official masters,
  not only target objects. This provides a same-cell clutter baseline.
  It never edits game records.
}

var
  OutList: TStringList;

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

function ParentLocation(e: IInterface): string;
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
        Result :=
          GetFileName(GetFile(c)) + '|' +
          Hex8(GetLoadOrderFormID(c)) + '|' +
          EditorID(c) + '|' +
          Name(c);
        exit;
      end;
    end;
    c := GetContainer(c);
  end;
end;

function Initialize: integer;
begin
  Result := 0;
  OutList := TStringList.Create;
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
    'full_path'
  );
  AddMessage('JANUS Bear context inventory exporter started.');
end;

function Process(e: IInterface): integer;
var
  recFile, kind: string;
  base, rootBase: IInterface;
  baseFixed: cardinal;
  p: TwbVector;
begin
  Result := 0;

  if ElementType(e) <> etMainRecord then exit;
  if Signature(e) <> 'REFR' then exit;

  recFile := GetFileName(GetFile(e));
  if not IsOfficialMaster(recFile) then exit;

  base := BaseRecord(e);
  if not Assigned(base) then exit;
  rootBase := MasterOrSelf(base);
  if not Assigned(rootBase) then rootBase := base;

  baseFixed := FixedFormID(rootBase);
  kind := TargetKind(baseFixed);
  p := GetPosition(e);

  OutList.Add(
    CleanTSV(recFile) + #9 +
    'REFR' + #9 +
    Hex8(GetLoadOrderFormID(e)) + #9 +
    CleanTSV(EditorID(e)) + #9 +
    kind + #9 +
    CleanTSV(GetFileName(GetFile(rootBase))) + #9 +
    CleanTSV(Signature(rootBase)) + #9 +
    Hex8(baseFixed) + #9 +
    CleanTSV(EditorID(rootBase)) + #9 +
    CleanTSV(Name(rootBase)) + #9 +
    CleanTSV(ParentLocation(e)) + #9 +
    BoolText(GetIsInitiallyDisabled(e)) + #9 +
    BoolText(GetIsDeleted(e)) + #9 +
    BoolText(GetIsPersistent(e)) + #9 +
    FloatToStr(p.x) + #9 +
    FloatToStr(p.y) + #9 +
    FloatToStr(p.z) + #9 +
    CleanTSV(FullPath(e))
  );
end;

function Finalize: integer;
var
  fn: string;
begin
  Result := 0;
  fn := ScriptsPath + 'JANUS-Teddy-Context-Inventory.tsv';
  OutList.SaveToFile(fn);
  AddMessage('JANUS Bear context inventory written: ' + fn);
  AddMessage('Rows including header: ' + IntToStr(OutList.Count));
  OutList.Free;
end;

end.
