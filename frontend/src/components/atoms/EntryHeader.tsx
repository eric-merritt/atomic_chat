import react, {useState} from 'react';

interface Account {
  name: string,
  isNormalCredit: boolean,
  isNormalDebit: boolean
}
function new_account(name: string, isNormalCredit: boolean, isNormalDebit: boolean) {
  const account: Account = {name, isNormalCredit, isNormalDebit}
  return account
}

interface Transaction {
  accounts: Account[],
  amount: number,
  date: Date,
  memo: string
} 

function new_transaction(accounts: Account[], amount: number, date: Date, memo: string) {
  const transaction: Transaction = {accounts, amount, date, memo}
  return transaction
}



export const EntryHeader = () => {

  return (
     <tr>
        <th>
        <td colSpan={1} className="date">DATE</td>
        <td colSpan={2} className="accounts">ACCOUNTS</td>
        <td colSpan={1} className="debit">DEBIT</td>
        <td colSpan={1} className="credit">CREDIT</td>
        </th>      
      </tr>
  )
};

export const AmountCell = () => {

  const [creditDebitSplit, setCreditDebitSplit] = useState({"debit": 0, "credit": 0});

  const handleInput = (e) => {
    const targetElement = e.target
    const isDebit: boolean = targetElement.nextSibling ? true : false;
    const isCredit: boolean = isDebit ? false : true

    if (isDebit) setCreditDebitSplit({"debit": targetElement.value, "credit": creditDebitSplit.credit})
    if (isCredit) setCreditDebitSplit({"debit": creditDebitSplit.debit, "credit": targetElement.value})
  }
  
  return (
    <td>
      <input type="phone" onInput={handleInput}/>
    </td>
  )
}


export const NormalDebitRow = () => {
  return (
      <tr>
        <td>
          <input type="text" placeholder="Date" className="text-center" />
        </td>
        <td colSpan={2}>
          <input placeholder="Account #1 Name"/>
        </td>
        <AmountCell/>
        <AmountCell/>
      </tr>
  )
}

export const NormalCreditRow = () => {
  return (
    <tr>
      <td>
        <input aria-disabled={true}></input>
      </td>
      <td colSpan={2}>
        <input placeholder="Account #2 Name" className="pl-2"/>
      </td>
      <AmountCell/>
      <AmountCell/>
    </tr>
  )
}

export const MemoRow = () => {
  return (
    <tr>
      <td>
        <input aria-disabled={true}/>
      </td>
      <td colSpan={2}>
        <input placeholder="Memo or description of transaction." type="text"/>
      </td>
      <td></td>
      <td></td>
    </tr>
  )
}

export default function JournalEntryForm() {
  return (
    <>
    <table>
      <EntryHeader/>
      <NormalDebitRow/>
      <NormalCreditRow/>
      <MemoRow/>      
    </table>
    </>
  )
}
