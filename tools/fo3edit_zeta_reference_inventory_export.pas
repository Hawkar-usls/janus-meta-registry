unit JANUS_Zeta_Reference_Inventory_Export;

{
  Read-only FO3Edit/xEdit exporter for Zeta.esm placed references.
  Select Zeta.esm and apply the script. Output:
  Edit Scripts\JANUS-Zeta-Reference-Inventory.tsv
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

function ParentLocation(e: IInterface): string;
var
  c: IInterface;
begin
  Result := '';
  c := GetContainer(e);
  while Assigned(c) do begin
    if ElementType(c) = etMainRecord then begin
      if (Signature(c) = 'CELL') or (Signature(c) = 'WRLD') then begin
        Result := ShortName(c) + ' ' + EditorID(c) + ' ' + Name(c);
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
    'record_editorid' + #9 + 'base_file' + #9 + 'base_signature' + #9 +
    'base_formid' + #9 + 'base_editorid' + #9 + 'base_name' + #9 +
    'parent_cell_or_world' + #9 + 'initially_disabled' + #9 + 'deleted' + #9 +
    'persistent' + #9 + 'position_x' + #9 + 'position_y' + #9 + 'position_z' + #9 +
    'full_path'
  );
end;

function Process(e: IInterface): integer;
var
  sig, recFile: string;
  base, rootBase: IInterface;
  baseFile, baseSig, baseForm, baseEdid, baseName: string;
  p: TwbVector;
begin
  Result := 0;
  if ElementType(e) <> etMainRecord then exit;

  recFile := GetFileName(GetFile(e));
  if CompareText(recFile, 'Zeta.esm') <> 0 then exit;

  sig := Signature(e);
  if (sig <> 'REFR') and (sig <> 'ACHR') and (sig <> 'ACRE') and
     (sig <> 'PGRE') and (sig <> 'PMIS') then exit;

  baseFile := '';
  baseSig := '';
  baseForm := '';
  baseEdid := '';
  baseName := '';

  base := BaseRecord(e);
  if Assigned(base) then begin
    rootBase := MasterOrSelf(base);
    if not Assigned(rootBase) then rootBase := base;
    baseFile := GetFileName(GetFile(rootBase));
    baseSig := Signature(rootBase);
    baseForm := IntToHex(FixedFormID(rootBase), 8);
    baseEdid := EditorID(rootBase);
    baseName := Name(rootBase);
  end;

  p := GetPosition(e);

  OutList.Add(
    CleanTSV(recFile) + #9 +
    sig + #9 +
    IntToHex(GetLoadOrderFormID(e), 8) + #9 +
    CleanTSV(EditorID(e)) + #9 +
    CleanTSV(baseFile) + #9 +
    CleanTSV(baseSig) + #9 +
    baseForm + #9 +
    CleanTSV(baseEdid) + #9 +
    CleanTSV(baseName) + #9 +
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
  fn := ScriptsPath + 'JANUS-Zeta-Reference-Inventory.tsv';
  OutList.SaveToFile(fn);
  AddMessage('JANUS Zeta reference inventory written: ' + fn);
  AddMessage('Rows including header: ' + IntToStr(OutList.Count));
  OutList.Free;
end;

end.
