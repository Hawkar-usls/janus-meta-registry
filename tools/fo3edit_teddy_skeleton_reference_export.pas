unit JANUS_Teddy_Skeleton_Reference_Export;

{
  Read-only Fallout 3 / official DLC reference exporter for teddy/skeleton
  environmental-storytelling analysis.

  Recommended use:
    1. Load Fallout3.esm and desired official DLC masters in FO3Edit/xEdit.
    2. Select the loaded master/plugin groups to process.
    3. Apply this script.
    4. Output: Edit Scripts\JANUS-Teddy-Skeleton-References.tsv
    5. Analyze with tools/analyze_teddy_skeleton_proximity.py

  This script never edits records.
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

function TargetKind(id: cardinal): string;
begin
  Result := '';
  if id = $0001F21F then Result := 'TEDDY'
  else if id = $0001EDEA then Result := 'SKELETON_CLOTHES'
  else if id = $0001EDE3 then Result := 'SKELETON_RAGS'
  else if id = $0002EC65 then Result := 'SKELETON_MALE'
  else if id = $0003DD2D then Result := 'SKELETON_FEMALE'
  else if id = $0003407A then Result := 'GNOME_GENERIC'
  else if id = $0005B634 then Result := 'GNOME_INTACT';
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
        Result := GetFileName(GetFile(c)) + '|' + Hex8(GetLoadOrderFormID(c)) + '|' +
                  EditorID(c) + '|' + Name(c);
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
    'record_file' + #9 + 'record_signature' + #9 + 'record_formid' + #9 +
    'record_editorid' + #9 + 'target_kind' + #9 + 'base_file' + #9 +
    'base_signature' + #9 + 'base_formid' + #9 + 'base_editorid' + #9 +
    'base_name' + #9 + 'location_key' + #9 + 'initially_disabled' + #9 +
    'deleted' + #9 + 'persistent' + #9 + 'position_x' + #9 + 'position_y' + #9 +
    'position_z' + #9 + 'full_path'
  );
  AddMessage('JANUS teddy/skeleton exporter started.');
end;

function Process(e: IInterface): integer;
var
  sig, recFile, kind: string;
  base, rootBase: IInterface;
  baseFixed: cardinal;
  p: TwbVector;
begin
  Result := 0;
  if ElementType(e) <> etMainRecord then exit;

  sig := Signature(e);
  if (sig <> 'REFR') and (sig <> 'ACHR') and (sig <> 'ACRE') then exit;

  base := BaseRecord(e);
  if not Assigned(base) then exit;
  rootBase := MasterOrSelf(base);
  if not Assigned(rootBase) then rootBase := base;

  baseFixed := FixedFormID(rootBase);
  kind := TargetKind(baseFixed);
  if kind = '' then exit;

  recFile := GetFileName(GetFile(e));
  p := GetPosition(e);

  OutList.Add(
    CleanTSV(recFile) + #9 +
    sig + #9 +
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
    FloatToStr(p.x) + #9 + FloatToStr(p.y) + #9 + FloatToStr(p.z) + #9 +
    CleanTSV(FullPath(e))
  );
end;

function Finalize: integer;
var
  fn: string;
begin
  Result := 0;
  fn := ScriptsPath + 'JANUS-Teddy-Skeleton-References.tsv';
  OutList.SaveToFile(fn);
  AddMessage('JANUS teddy/skeleton reference export written: ' + fn);
  AddMessage('Rows including header: ' + IntToStr(OutList.Count));
  OutList.Free;
end;

end.
