unit JANUS_Zeta_Birthday_Lineage_Export;

{
  JANUS / Mothership Zeta birthday-happy-place lineage exporter.
  Intended for FO3Edit/xEdit with Fallout3.esm and Zeta.esm loaded.

  Recommended use:
    1. Load Fallout3.esm and Zeta.esm in FO3Edit.
    2. In the left tree select Zeta.esm (the whole plugin).
    3. Apply this script.
    4. The script writes Edit Scripts\JANUS-Zeta-Birthday-Lineage.tsv.
    5. Run tools/verify_zeta_birthday_lineage_receipt.py on the TSV.

  Read-only: this script never edits game records.
}

var
  OutList: TStringList;
  OutPath: string;

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

function IsBirthdayTarget(id: cardinal): boolean;
begin
  Result :=
    (id = $00028FF8) or  { Kid's party hat }
    (id = $00050E44) or  { Party hat }
    (id = $0009FAED) or  { Birthday balloons family }
    (id = $0009AE97) or  { Birthday banner }
    (id = $0009AE98) or  { Birthday cake static }
    (id = $0009FE61);    { Birthday cake FX }
end;

function KeywordReason(s: string): string;
var
  t: string;
begin
  Result := '';
  t := LowerCase(s);
  if Pos('birthday', t) > 0 then Result := Result + 'keyword:birthday,';
  if Pos('party', t) > 0 then Result := Result + 'keyword:party,';
  if Pos('balloon', t) > 0 then Result := Result + 'keyword:balloon,';
  if Pos('cake', t) > 0 then Result := Result + 'keyword:cake,';
  if Pos('vault101', t) > 0 then Result := Result + 'keyword:vault101,';
  if Pos('cg02', t) > 0 then Result := Result + 'keyword:cg02,';
  if Pos('dlc05mz1', t) > 0 then Result := Result + 'keyword:dlc05mz1,';
  if Pos('abduction', t) > 0 then Result := Result + 'keyword:abduction,';
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
    'record_file' + #9 +
    'record_signature' + #9 +
    'record_formid' + #9 +
    'record_editorid' + #9 +
    'base_file' + #9 +
    'base_signature' + #9 +
    'base_formid' + #9 +
    'base_editorid' + #9 +
    'base_name' + #9 +
    'parent_cell_or_world' + #9 +
    'initially_disabled' + #9 +
    'deleted' + #9 +
    'persistent' + #9 +
    'position_x' + #9 +
    'position_y' + #9 +
    'position_z' + #9 +
    'full_path' + #9 +
    'match_reason'
  );
  AddMessage('JANUS Zeta birthday lineage exporter: select/process Zeta.esm.');
end;

function Process(e: IInterface): integer;
var
  recFile, recSig, recForm, recEdid: string;
  base, rootBase: IInterface;
  baseFile, baseSig, baseForm, baseEdid, baseName: string;
  haystack, reason, loc: string;
  baseFixed: cardinal;
  posv: TwbVector;
  px, py, pz: string;
  hasBase, isTarget, isKeyword: boolean;
begin
  Result := 0;

  if ElementType(e) <> etMainRecord then exit;
  recFile := GetFileName(GetFile(e));

  { Hard boundary: only records physically contained by Zeta.esm are exported. }
  if CompareText(recFile, 'Zeta.esm') <> 0 then exit;

  recSig := Signature(e);
  recForm := Hex8(GetLoadOrderFormID(e));
  recEdid := EditorID(e);

  baseFile := '';
  baseSig := '';
  baseForm := '';
  baseEdid := '';
  baseName := '';
  baseFixed := 0;
  hasBase := false;

  base := BaseRecord(e);
  if Assigned(base) then begin
    rootBase := MasterOrSelf(base);
    if not Assigned(rootBase) then rootBase := base;
    hasBase := true;
    baseFile := GetFileName(GetFile(rootBase));
    baseSig := Signature(rootBase);
    baseForm := Hex8(FixedFormID(rootBase));
    baseEdid := EditorID(rootBase);
    baseName := Name(rootBase);
    baseFixed := FixedFormID(rootBase);
  end;

  haystack := recEdid + ' ' + Name(e) + ' ' + FullPath(e) + ' ' +
              baseEdid + ' ' + baseName;
  reason := KeywordReason(haystack);
  isKeyword := reason <> '';
  isTarget := hasBase and IsBirthdayTarget(baseFixed);

  if isTarget then
    reason := 'target_base_form:' + Hex8(baseFixed) + ',' + reason;

  { Keep exact birthday targets and broader residue candidates. }
  if (not isTarget) and (not isKeyword) then exit;

  loc := ParentLocation(e);
  px := '';
  py := '';
  pz := '';

  if (recSig = 'REFR') or (recSig = 'ACHR') or (recSig = 'ACRE') or
     (recSig = 'PGRE') or (recSig = 'PMIS') then begin
    posv := GetPosition(e);
    px := FloatToStr(posv.x);
    py := FloatToStr(posv.y);
    pz := FloatToStr(posv.z);
  end;

  OutList.Add(
    CleanTSV(recFile) + #9 +
    CleanTSV(recSig) + #9 +
    recForm + #9 +
    CleanTSV(recEdid) + #9 +
    CleanTSV(baseFile) + #9 +
    CleanTSV(baseSig) + #9 +
    baseForm + #9 +
    CleanTSV(baseEdid) + #9 +
    CleanTSV(baseName) + #9 +
    CleanTSV(loc) + #9 +
    BoolText(GetIsInitiallyDisabled(e)) + #9 +
    BoolText(GetIsDeleted(e)) + #9 +
    BoolText(GetIsPersistent(e)) + #9 +
    px + #9 + py + #9 + pz + #9 +
    CleanTSV(FullPath(e)) + #9 +
    CleanTSV(reason)
  );
end;

function Finalize: integer;
begin
  Result := 0;
  OutPath := ScriptsPath + 'JANUS-Zeta-Birthday-Lineage.tsv';
  OutList.SaveToFile(OutPath);
  AddMessage('JANUS Zeta birthday lineage export written: ' + OutPath);
  AddMessage('Rows including header: ' + IntToStr(OutList.Count));
  OutList.Free;
end;

end.
