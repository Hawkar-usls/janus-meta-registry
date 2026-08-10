unit fo3edit_braun_privileged_memory_bridge_audit_v1_3;

{
  JANUS / Fallout 3 — Braun privileged memory-bridge discovery audit v1.3

  Read-only discovery tool. Load exactly:
    Fallout3.esm
    Anchorage.esm
    ThePitt.esm
    BrokenSteel.esm
    PointLookout.esm
    Zeta.esm

  Apply to all loaded records/groups.

  Outputs:
    Edit Scripts\JANUS-Braun-Memory-Bridge-Candidates-v1.3.tsv
    Edit Scripts\JANUS-Braun-Seed-Reverse-Refs-v1.3.tsv

  IMPORTANT:
    A keyword hit or reverse reference is only a discovery candidate.
    It is NOT by itself a James->memory-carrier write/export edge.
}

var
  CandidateOut: TStringList;
  ReverseOut: TStringList;
  LoadedOfficial: TStringList;
  UnexpectedPlugins: TStringList;
  SeenWinning: TStringList;
  Keywords: TStringList;
  Blocked: boolean;
  DuplicateWinningCount: integer;

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

function IsWinningEffective(e: IInterface): boolean;
var
  root: IInterface;
  ovCount: integer;
begin
  Result := false;
  if not Assigned(e) then exit;
  if ElementType(e) <> etMainRecord then exit;
  root := MasterOrSelf(e);
  if not Assigned(root) then root := e;
  ovCount := OverrideCount(root);
  if IsMaster(e) then begin
    if ovCount = 0 then Result := true;
  end else if IsWinningOverride(e) then
    Result := true;
end;

function IsSeedFixedFormID(id: cardinal): boolean;
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
    (id = $000C339F) or  { MQ04FailsafeTerminalVersionControlSubMenu }
    (id = $00024D62) or  { MS08PinkertonLog1 }
    (id = $00024D63) or  { MS08PinkertonLog2 }
    (id = $00024D64);    { MS08PinkertonLog3 }
end;

function SeedLabel(id: cardinal): string;
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
  else if id = $000C339F then Result := 'MQ04FailsafeTerminalVersionControlSubMenu'
  else if id = $00024D62 then Result := 'MS08PinkertonLog1'
  else if id = $00024D63 then Result := 'MS08PinkertonLog2'
  else if id = $00024D64 then Result := 'MS08PinkertonLog3';
end;

function FindKeyword(text: string): string;
var
  i: integer;
  t, k: string;
begin
  Result := '';
  t := Lower(text);
  for i := 0 to Keywords.Count - 1 do begin
    k := Keywords[i];
    if Pos(k, t) > 0 then begin
      Result := k;
      exit;
    end;
  end;
end;

procedure EmitCandidate(rec, el: IInterface; keyword, value: string);
var
  root: IInterface;
  rootID: cardinal;
  elementPath: string;
begin
  if Length(value) > 2000 then value := Copy(value, 1, 2000) + '...[TRUNCATED]';
  root := MasterOrSelf(rec);
  if not Assigned(root) then root := rec;
  rootID := FixedFormID(root);
  elementPath := CleanTSV(Path(el));
  CandidateOut.Add(
    CleanTSV(GetFileName(GetFile(rec))) + #9 +
    CleanTSV(Signature(rec)) + #9 +
    Hex8(GetLoadOrderFormID(rec)) + #9 +
    Hex8(rootID) + #9 +
    CleanTSV(EditorID(rec)) + #9 +
    CleanTSV(Name(rec)) + #9 +
    keyword + #9 +
    elementPath + #9 +
    CleanTSV(value) + #9 +
    BoolToStr(IsSeedFixedFormID(rootID), true) + #9 +
    CleanTSV(SeedLabel(rootID)) + #9 +
    CleanTSV(FullPath(rec))
  );
end;

procedure ScanElement(rec, el: IInterface; depth: integer);
var
  i, n: integer;
  child: IInterface;
  value, combined, kw: string;
begin
  if not Assigned(el) then exit;
  if depth > 32 then exit;

  n := ElementCount(el);
  if n > 0 then begin
    for i := 0 to n - 1 do begin
      child := ElementByIndex(el, i);
      if Assigned(child) then ScanElement(rec, child, depth + 1);
    end;
    exit;
  end;

  value := GetEditValue(el);
  if value = '' then exit;
  combined := Name(el) + ' ' + value;
  kw := FindKeyword(combined);
  if kw <> '' then EmitCandidate(rec, el, kw, value);
end;

procedure ExportSeedReverseRefs(e: IInterface);
var
  root, r: IInterface;
  rootID: cardinal;
  i, n: integer;
  fn: string;
begin
  root := MasterOrSelf(e);
  if not Assigned(root) then root := e;
  rootID := FixedFormID(root);
  if not IsSeedFixedFormID(rootID) then exit;

  n := ReferencedByCount(root);
  for i := 0 to n - 1 do begin
    r := ReferencedByIndex(root, i);
    if not Assigned(r) then continue;
    fn := GetFileName(GetFile(r));
    if not IsOfficialMaster(fn) then continue;
    ReverseOut.Add(
      Hex8(rootID) + #9 +
      CleanTSV(SeedLabel(rootID)) + #9 +
      CleanTSV(GetFileName(GetFile(root))) + #9 +
      CleanTSV(Signature(root)) + #9 +
      CleanTSV(fn) + #9 +
      CleanTSV(Signature(r)) + #9 +
      Hex8(GetLoadOrderFormID(r)) + #9 +
      CleanTSV(EditorID(r)) + #9 +
      CleanTSV(Name(r)) + #9 +
      CleanTSV(FullPath(r))
    );
  end;
end;

procedure AddKeywords;
begin
  Keywords.Add('memory');
  Keywords.Add('mem chip');
  Keywords.Add('memory chip');
  Keywords.Add('memchip');
  Keywords.Add('neural');
  Keywords.Add('neuralizer');
  Keywords.Add('engram');
  Keywords.Add('copy');
  Keywords.Add('write');
  Keywords.Add('rewrite');
  Keywords.Add('export');
  Keywords.Add('transfer');
  Keywords.Add('overwrite');
  Keywords.Add('serialize');
  Keywords.Add('persist');
  Keywords.Add('backup');
  Keywords.Add('braun');
  Keywords.Add('vault112');
  Keywords.Add('vault 112');
  Keywords.Add('mq04doc');
  Keywords.Add('vault112podtermdad');
  Keywords.Add('mq04statusnotedad');
  Keywords.Add('mq04stressnotedad');
  Keywords.Add('additem');
  Keywords.Add('removeitem');
  Keywords.Add('removeallitems');
  Keywords.Add('moveto');
  Keywords.Add('enable');
  Keywords.Add('disable');
  Keywords.Add('user unknown');
end;

function Initialize: integer;
var
  i: integer;
  f: IInterface;
  fn: string;
begin
  Result := 0;
  Blocked := false;
  DuplicateWinningCount := 0;

  CandidateOut := TStringList.Create;
  ReverseOut := TStringList.Create;
  LoadedOfficial := TStringList.Create;
  UnexpectedPlugins := TStringList.Create;
  SeenWinning := TStringList.Create;
  Keywords := TStringList.Create;

  LoadedOfficial.Sorted := true;
  LoadedOfficial.Duplicates := dupIgnore;
  UnexpectedPlugins.Sorted := true;
  UnexpectedPlugins.Duplicates := dupIgnore;
  SeenWinning.Sorted := true;
  SeenWinning.Duplicates := dupIgnore;
  Keywords.Sorted := true;
  Keywords.Duplicates := dupIgnore;
  AddKeywords;

  if CompareText(wbAppName, 'FO3') <> 0 then begin
    AddMessage('JANUS Braun v1.3 BLOCKED: xEdit is not running in FO3 mode.');
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
    AddMessage('JANUS Braun v1.3 BLOCKED: expected six official masters, found ' + IntToStr(LoadedOfficial.Count) + '.');
    Blocked := true;
  end;
  if UnexpectedPlugins.Count > 0 then begin
    AddMessage('JANUS Braun v1.3 BLOCKED: non-official plugins loaded.');
    Blocked := true;
  end;

  CandidateOut.Add(
    'record_file' + #9 + 'record_signature' + #9 + 'record_formid' + #9 +
    'root_fixed_formid' + #9 + 'record_editorid' + #9 + 'record_name' + #9 +
    'matched_keyword' + #9 + 'element_path' + #9 + 'element_value' + #9 +
    'is_seed_record' + #9 + 'seed_label' + #9 + 'record_full_path'
  );
  ReverseOut.Add(
    'seed_fixed_formid' + #9 + 'seed_label' + #9 + 'seed_file' + #9 + 'seed_signature' + #9 +
    'referencing_file' + #9 + 'referencing_signature' + #9 + 'referencing_formid' + #9 +
    'referencing_editorid' + #9 + 'referencing_name' + #9 + 'referencing_full_path'
  );

  AddMessage('JANUS Braun privileged memory bridge audit v1.3 initialized.');
end;

function Process(e: IInterface): integer;
var
  fn, logicalID: string;
  root: IInterface;
begin
  Result := 0;
  if Blocked then exit;
  if ElementType(e) <> etMainRecord then exit;
  fn := GetFileName(GetFile(e));
  if not IsOfficialMaster(fn) then exit;
  if not IsWinningEffective(e) then exit;
  if GetIsDeleted(e) then exit;

  root := MasterOrSelf(e);
  if not Assigned(root) then root := e;
  logicalID := Hex8(GetLoadOrderFormID(root));
  if SeenWinning.IndexOf(logicalID) >= 0 then begin
    DuplicateWinningCount := DuplicateWinningCount + 1;
    exit;
  end;
  SeenWinning.Add(logicalID);

  ExportSeedReverseRefs(e);

  { Scan every effective official record class. Record header identity is also
    scanned explicitly because EditorID/Name may not be represented as a leaf
    by all xEdit definitions. }
  if FindKeyword(EditorID(e) + ' ' + Name(e)) <> '' then
    EmitCandidate(e, e, FindKeyword(EditorID(e) + ' ' + Name(e)), EditorID(e) + ' | ' + Name(e));
  ScanElement(e, e, 0);
end;

function Finalize: integer;
var
  candidateFn, reverseFn: string;
begin
  Result := 0;
  if Blocked then begin
    AddMessage('JANUS Braun v1.3 export NOT WRITTEN: admission prerequisites failed.');
  end else if DuplicateWinningCount <> 0 then begin
    AddMessage('JANUS Braun v1.3 export NOT WRITTEN: duplicate effective logical records = ' + IntToStr(DuplicateWinningCount));
  end else begin
    candidateFn := ScriptsPath + 'JANUS-Braun-Memory-Bridge-Candidates-v1.3.tsv';
    reverseFn := ScriptsPath + 'JANUS-Braun-Seed-Reverse-Refs-v1.3.tsv';
    CandidateOut.SaveToFile(candidateFn);
    ReverseOut.SaveToFile(reverseFn);
    AddMessage('Candidate hits: ' + IntToStr(CandidateOut.Count - 1));
    AddMessage('Seed reverse-reference edges: ' + IntToStr(ReverseOut.Count - 1));
    AddMessage('Candidates: ' + candidateFn);
    AddMessage('Reverse refs: ' + reverseFn);
  end;

  CandidateOut.Free;
  ReverseOut.Free;
  LoadedOfficial.Free;
  UnexpectedPlugins.Free;
  SeenWinning.Free;
  Keywords.Free;
end;

end.
